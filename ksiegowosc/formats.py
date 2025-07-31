# ksiegowosc/formats.py

from import_export.formats.base_formats import Format
from tablib import Dataset
import xml.etree.ElementTree as ET
from .models import Contractor
from decimal import Decimal, InvalidOperation
from datetime import datetime
import io

class JPKXMLFormat(Format):
    """Custom format dla importu plików JPK_FA XML - faktury"""
    
    def get_title(self):
        return "JPK XML"

    def get_extension(self):
        return "xml"

    def can_import(self):
        return True

    def can_export(self):
        return False

    def is_binary(self):
        return False

    def get_read_mode(self):
        return 'r'

    def create_dataset(self, in_stream, **kwargs):
        """
        Główna metoda konwertująca XML JPK_FA na dataset tablib
        """
        user = kwargs.get('user')
        if not user:
            raise ValueError("User jest wymagany do importu JPK")
            
        new_dataset = Dataset()
        
        # Nagłówki muszą dokładnie odpowiadać polom w InvoiceResource
        new_dataset.headers = [
            'invoice_number', 'issue_date', 'sale_date', 
            'contractor_tax_id', 'contractor_name', 'total_amount', 
            'is_correction'
        ]

        # Sprawdzamy czy in_stream to plik czy string
        if hasattr(in_stream, 'read'):
            xml_content = in_stream.read()
        else:
            xml_content = in_stream
            
        # Jeśli to bytes, konwertuj na string
        if isinstance(xml_content, bytes):
            try:
                xml_content = xml_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    xml_content = xml_content.decode('windows-1250')
                except UnicodeDecodeError:
                    xml_content = xml_content.decode('iso-8859-2')

        # Sprawdź czy to rzeczywiście plik JPK
        if 'JPK' not in xml_content and 'Faktura' not in xml_content:
            raise ValueError("Plik nie zawiera danych JPK_FA. Sprawdź czy wybrałeś właściwy plik XML.")

        # Namespace dla JPK_FA - spróbuj różne wersje
        namespaces = [
            {'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/'},
            {'tns': 'http://jpk.mf.gov.pl/wzor/2021/03/09/03091/'},
            {'tns': 'http://jpk.mf.gov.pl/wzor/2020/03/09/03091/'},
            {'': ''}  # fallback bez namespace
        ]
        
        root = None
        ns = None
        
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}. Sprawdź czy plik nie jest uszkodzony.")

        # Znajdź właściwy namespace
        for test_ns in namespaces:
            faktury = root.findall('tns:Faktura' if 'tns' in test_ns else 'Faktura', test_ns)
            if faktury:
                ns = test_ns
                break
        
        if ns is None:
            # Spróbuj bez namespace
            faktury = root.findall('.//Faktura')
            if faktury:
                ns = {'': ''}
            else:
                raise ValueError("Nie znaleziono elementów 'Faktura' w pliku JPK. Sprawdź czy to właściwy format JPK_FA.")

        # Parsujemy faktury z XML
        faktury_count = 0
        for faktura_node in root.findall('tns:Faktura' if 'tns' in ns else './/Faktura', ns):
            try:
                row_data = self._parse_faktura_node(faktura_node, ns, user)
                if row_data:
                    new_dataset.append(row_data)
                    faktury_count += 1
            except Exception as e:
                print(f"Błąd przetwarzania faktury: {str(e)}")
                continue

        if faktury_count == 0:
            raise ValueError("Nie znaleziono żadnych poprawnych faktur w pliku JPK. Sprawdź strukturę pliku XML.")

        return new_dataset

    def _parse_faktura_node(self, faktura_node, ns, user):
        """
        Parsuje pojedynczy node faktury z XML
        """
        def get_text(node, path):
            """Bezpieczne pobieranie tekstu z node'a XML"""
            # Spróbuj z namespace
            if 'tns' in ns:
                found_node = node.find(f'tns:{path}', ns)
            else:
                found_node = node.find(path)
                
            if found_node is not None and found_node.text:
                return found_node.text.strip()
            return None

        def parse_date(date_str):
            """Parsuje datę z różnych formatów"""
            if not date_str:
                return None
            try:
                # Spróbuj format YYYY-MM-DD
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    # Spróbuj format DD-MM-YYYY
                    return datetime.strptime(date_str, '%d-%m-%Y').date()
                except ValueError:
                    try:
                        # Spróbuj format YYYY/MM/DD
                        return datetime.strptime(date_str, '%Y/%m/%d').date()
                    except ValueError:
                        return None

        def parse_decimal(value_str):
            """Parsuje wartość dziesiętną"""
            if not value_str:
                return Decimal('0.00')
            try:
                # Zamień przecinek na kropkę dla wartości dziesiętnych
                cleaned_value = value_str.replace(',', '.').replace(' ', '')
                return Decimal(cleaned_value)
            except (InvalidOperation, ValueError):
                return Decimal('0.00')

        # Pobieramy podstawowe dane faktury - różne pola w różnych wersjach JPK
        possible_invoice_fields = ['P_2A', '2A', 'NrFaktury']
        possible_buyer_nip_fields = ['P_5B', '5B', 'NIP']
        possible_buyer_name_fields = ['P_3A', '3A', 'Nazwa']
        possible_date_fields = ['P_1', '1', 'DataWystawienia']
        possible_sale_date_fields = ['P_6', '6', 'DataSprzedazy']
        possible_amount_fields = ['P_15', '15', 'WartoscBrutto']

        invoice_number = None
        for field in possible_invoice_fields:
            invoice_number = get_text(faktura_node, field)
            if invoice_number:
                break

        nabywca_nip = None
        for field in possible_buyer_nip_fields:
            nabywca_nip = get_text(faktura_node, field)
            if nabywca_nip:
                break

        nabywca_name = None
        for field in possible_buyer_name_fields:
            nabywca_name = get_text(faktura_node, field)
            if nabywca_name:
                break

        issue_date_str = None
        for field in possible_date_fields:
            issue_date_str = get_text(faktura_node, field)
            if issue_date_str:
                break

        sale_date_str = None
        for field in possible_sale_date_fields:
            sale_date_str = get_text(faktura_node, field)
            if sale_date_str:
                break

        total_amount_str = None
        for field in possible_amount_fields:
            total_amount_str = get_text(faktura_node, field)
            if total_amount_str:
                break

        # Sprawdzamy czy mamy wymagane dane
        if not invoice_number:
            print(f"Pominięto fakturę - brak numeru faktury")
            return None
            
        if not nabywca_nip:
            print(f"Pominięto fakturę {invoice_number} - brak NIP nabywcy")
            return None

        # Parsujemy daty
        issue_date = parse_date(issue_date_str)
        sale_date = parse_date(sale_date_str)
        
        if not issue_date:
            issue_date = datetime.now().date()
        if not sale_date:
            sale_date = issue_date

        # Parsujemy kwotę
        total_amount = parse_decimal(total_amount_str)

        # Sprawdzamy czy to korekta
        is_correction = False
        rodzaj_node = faktura_node.find('tns:RodzajFaktury' if 'tns' in ns else 'RodzajFaktury', ns)
        if rodzaj_node is not None and rodzaj_node.text:
            is_correction = 'KOREKTA' in rodzaj_node.text.upper()

        # Zwracamy wiersz danych
        return [
            invoice_number,
            issue_date,
            sale_date,
            nabywca_nip,  # contractor_tax_id - widget znajdzie lub utworzy kontrahenta
            nabywca_name or 'Brak nazwy',  # contractor_name
            total_amount,
            is_correction
        ]

    def export_data(self, dataset, **kwargs):
        """Export nie jest wspierany dla JPK"""
        raise NotImplementedError("Export do formatu JPK nie jest wspierany")


class JPKXMLFormatItems(Format):
    """Custom format dla importu pozycji faktur z JPK_FA XML"""
    
    def get_title(self):
        return "JPK XML (pozycje)"

    def get_extension(self):
        return "xml"

    def can_import(self):
        return True

    def can_export(self):
        return False

    def is_binary(self):
        return False

    def get_read_mode(self):
        return 'r'

    def create_dataset(self, in_stream, **kwargs):
        """
        Konwertuje XML JPK_FA na dataset pozycji faktur
        """
        user = kwargs.get('user')
        if not user:
            raise ValueError("User jest wymagany do importu JPK")
            
        new_dataset = Dataset()
        
        # Nagłówki dla pozycji faktury
        new_dataset.headers = [
            'invoice_number', 'name', 'quantity', 'unit', 'unit_price', 'total_price'
        ]

        # Sprawdzamy czy in_stream to plik czy string
        if hasattr(in_stream, 'read'):
            xml_content = in_stream.read()
        else:
            xml_content = in_stream
            
        # Jeśli to bytes, konwertuj na string
        if isinstance(xml_content, bytes):
            try:
                xml_content = xml_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    xml_content = xml_content.decode('windows-1250')
                except UnicodeDecodeError:
                    xml_content = xml_content.decode('iso-8859-2')

        # Sprawdź czy to rzeczywiście plik JPK
        if 'JPK' not in xml_content and 'Faktura' not in xml_content:
            raise ValueError("Plik nie zawiera danych JPK_FA. Sprawdź czy wybrałeś właściwy plik XML.")

        # Namespace dla JPK_FA - spróbuj różne wersje
        namespaces = [
            {'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/'},
            {'tns': 'http://jpk.mf.gov.pl/wzor/2021/03/09/03091/'},
            {'tns': 'http://jpk.mf.gov.pl/wzor/2020/03/09/03091/'},
            {'': ''}  # fallback bez namespace
        ]
        
        root = None
        ns = None
        
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}. Sprawdź czy plik nie jest uszkodzony.")

        # Znajdź właściwy namespace
        for test_ns in namespaces:
            faktury = root.findall('tns:Faktura' if 'tns' in test_ns else 'Faktura', test_ns)
            if faktury:
                ns = test_ns
                break
        
        if ns is None:
            # Spróbuj bez namespace
            faktury = root.findall('.//Faktura')
            if faktury:
                ns = {'': ''}
            else:
                raise ValueError("Nie znaleziono elementów 'Faktura' w pliku JPK. Sprawdź czy to właściwy format JPK_FA.")

        # Parsujemy pozycje z każdej faktury
        items_count = 0
        for faktura_node in root.findall('tns:Faktura' if 'tns' in ns else './/Faktura', ns):
            try:
                items_data = self._parse_items_from_faktura(faktura_node, ns, user)
                for item_data in items_data:
                    if item_data:
                        new_dataset.append(item_data)
                        items_count += 1
            except Exception as e:
                print(f"Błąd przetwarzania pozycji faktury: {str(e)}")
                continue

        if items_count == 0:
            raise ValueError("Nie znaleziono żadnych pozycji w pliku JPK. Sprawdź strukturę pliku XML.")

        return new_dataset

    def _parse_items_from_faktura(self, faktura_node, ns, user):
        """
        Parsuje pozycje z pojedynczej faktury
        """
        def get_text(node, path):
            """Bezpieczne pobieranie tekstu z node'a XML"""
            # Spróbuj z namespace
            if 'tns' in ns:
                found_node = node.find(f'tns:{path}', ns)
            else:
                found_node = node.find(path)
                
            if found_node is not None and found_node.text:
                return found_node.text.strip()
            return None

        def parse_decimal(value_str):
            """Parsuje wartość dziesiętną"""
            if not value_str:
                return Decimal('0.00')
            try:
                cleaned_value = value_str.replace(',', '.').replace(' ', '')
                return Decimal(cleaned_value)
            except (InvalidOperation, ValueError):
                return Decimal('0.00')

        items_data = []
        
        # Pobierz numer faktury
        invoice_number = get_text(faktura_node, 'P_2A') or get_text(faktura_node, '2A')
        if not invoice_number:
            return items_data

        # 1. Sprawdź pozycję w głównym węźle faktury
        service_desc = get_text(faktura_node, 'P_7') or get_text(faktura_node, '7')
        if service_desc:
            quantity_str = get_text(faktura_node, 'P_8A') or get_text(faktura_node, '8A')
            unit_str = get_text(faktura_node, 'P_8B') or get_text(faktura_node, '8B')
            unit_price_str = get_text(faktura_node, 'P_9A') or get_text(faktura_node, '9A')
            value_str = get_text(faktura_node, 'P_11') or get_text(faktura_node, '11')
            
            quantity = parse_decimal(quantity_str) if quantity_str else Decimal('1.00')
            unit = unit_str if unit_str else 'szt.'
            unit_price = parse_decimal(unit_price_str) if unit_price_str else Decimal('0.00')
            total_price = parse_decimal(value_str) if value_str else (quantity * unit_price)
            
            items_data.append([
                invoice_number,
                service_desc,
                quantity,
                unit,
                unit_price,
                total_price
            ])

        # 2. Sprawdź dedykowane węzły pozycji
        possible_item_paths = [
            'FakturaWiersz', 'Wiersz', 'PozycjaFaktury'
        ]
        
        item_nodes = []
        for path in possible_item_paths:
            if 'tns' in ns:
                found_items = faktura_node.findall(f'tns:{path}', ns)
            else:
                found_items = faktura_node.findall(f'.//{path}')
            if found_items:
                item_nodes = found_items
                break

        for i, item_node in enumerate(item_nodes):
            try:
                item_name = (get_text(item_node, 'P_7') or 
                           get_text(item_node, '7') or 
                           get_text(item_node, 'NazwaTowaru') or 
                           f"Pozycja {i+1}")
                
                quantity_str = get_text(item_node, 'P_8A') or get_text(item_node, '8A')
                unit_str = get_text(item_node, 'P_8B') or get_text(item_node, '8B')
                unit_price_str = get_text(item_node, 'P_9A') or get_text(item_node, '9A')
                value_str = get_text(item_node, 'P_11') or get_text(item_node, '11')
                
                quantity = parse_decimal(quantity_str) if quantity_str else Decimal('1.00')
                unit = unit_str if unit_str else 'szt.'
                unit_price = parse_decimal(unit_price_str) if unit_price_str else Decimal('0.00')
                total_price = parse_decimal(value_str) if value_str else (quantity * unit_price)
                
                if unit_price == 0 and total_price > 0 and quantity > 0:
                    unit_price = total_price / quantity
                
                items_data.append([
                    invoice_number,
                    item_name,
                    quantity,
                    unit,
                    unit_price,
                    total_price
                ])
                
            except Exception as e:
                print(f"Błąd przetwarzania pozycji {i+1}: {str(e)}")
                continue

        return items_data