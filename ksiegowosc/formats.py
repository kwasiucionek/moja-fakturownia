# ksiegowosc/formats.py

from import_export.formats.base_formats import Format
from tablib import Dataset
import xml.etree.ElementTree as ET
from .models import Contractor

class JPKXMLFormat(Format):
    def get_title(self):
        return "xml"

    def get_extension(self):
        return "xml"

    def can_import(self):
        return True

    def create_dataset(self, in_stream, **kwargs):
        """
        This is the core of the converter. It reads the XML and creates tabular data.
        """
        user = kwargs.get('user')
        new_dataset = Dataset()
        # The headers must exactly match the 'fields' in your InvoiceResource Meta class
        new_dataset.headers = ['id', 'invoice_number', 'issue_date', 'sale_date', 'contractor', 'total_amount', 'is_correction', 'user']

        xml_string = in_stream.read()
        if isinstance(xml_string, bytes):
            xml_string = xml_string.decode('utf-8')

        ns = {'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/'}
        root = ET.fromstring(xml_string)

        for faktura_node in root.findall('tns:Faktura', ns):
            # Helper function to safely get text from a node
            def get_text(node, path):
                found_node = node.find(path, ns)
                return found_node.text if found_node is not None else None

            # Safely extract all data, providing defaults if tags are missing
            invoice_number = get_text(faktura_node, 'tns:P_2A')
            nabywca_nip = get_text(faktura_node, 'tns:P_5B')
            nabywca_name = get_text(faktura_node, 'tns:P_3A')

            if not invoice_number or not nabywca_nip:
                continue # Skip invoice if essential data is missing

            contractor, _ = Contractor.objects.get_or_create(
                tax_id=nabywca_nip,
                user=user,
                defaults={'name': nabywca_name or 'Brak nazwy'}
            )

            rodzaj_faktury_node = faktura_node.find('tns:RodzajFaktury', ns)
            is_corr = (rodzaj_faktury_node is not None and rodzaj_faktury_node.text == 'KOREKTA')

            new_dataset.append([
                None,
                invoice_number,
                get_text(faktura_node, 'tns:P_1'),
                get_text(faktura_node, 'tns:P_6'),
                contractor.id,
                get_text(faktura_node, 'tns:P_15'),
                is_corr,
                user.id if user else None
            ])

        return new_dataset
