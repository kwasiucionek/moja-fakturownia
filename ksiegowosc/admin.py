# ksiegowosc/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import CompanyInfo, Contractor, Invoice, InvoiceItem, MonthlySettlement
from django.contrib import messages
from django.db.models import Sum
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
from django.db import transaction
import csv

# Dodaj to do ksiegowosc/admin.py na początku, zastępując obecny CompanyInfoAdmin

# Dodaj to do ksiegowosc/admin.py na początku, zastępując obecny CompanyInfoAdmin

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'tax_id', 'business_type', 'income_tax_type', 'vat_settlement', 'user')
    list_filter = ('business_type', 'income_tax_type', 'vat_settlement', 'vat_payer', 'zus_payer')
    search_fields = ('company_name', 'tax_id', 'regon', 'krs')
    exclude = ('user',)

    fieldsets = (
        ('Dane identyfikacyjne', {
            'fields': (
                'company_name',
                'short_name',
                'business_type',
                'tax_id',
                'regon',
                'krs',
                'pkd_code',
                'pkd_description'
            )
        }),
        ('Adres', {
            'fields': (
                'street',
                'zip_code',
                'city',
                'voivodeship',
                'country'
            )
        }),
        ('Dane kontaktowe', {
            'fields': (
                'phone',
                'fax',
                'email',
                'website'
            )
        }),
        ('Rachunek bankowy', {
            'fields': (
                'bank_account_number',
                'bank_name',
                'bank_swift'
            )
        }),
        ('Podatki dochodowe', {
            'fields': (
                'income_tax_type',
                'lump_sum_rate',
                'business_start_date',
                'tax_year_start'
            ),
            'description': 'Ustawienia dotyczące podatku dochodowego od osób fizycznych lub prawnych'
        }),
        ('Podatek od towarów i usług VAT', {
            'fields': (
                'vat_payer',
                'vat_settlement',
                'vat_id',
                'vat_cash_method',
                'small_taxpayer_vat'
            ),
            'description': 'Ustawienia dotyczące podatku VAT'
        }),
        ('Rozliczenia z Zakładem Ubezpieczeń Społecznych', {
            'fields': (
                'zus_payer',
                'zus_number',
                'zus_code',
                'preferential_zus',
                'small_zus_plus',
                'zus_health_insurance_only'
            ),
            'description': 'Ustawienia dotyczące składek ZUS'
        }),
        ('Księgowość i ewidencja', {
            'fields': (
                'accounting_method',
                'electronic_invoices',
                'jpk_fa_required'
            ),
            'description': 'Ustawienia dotyczące prowadzenia ewidencji księgowej'
        }),
        ('Przedstawiciel ustawowy', {
            'fields': (
                'legal_representative_name',
                'legal_representative_position'
            ),
            'classes': ('collapse',),
            'description': 'Dane przedstawiciela ustawowego (dla spółek)'
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    class Media:
        css = {
            'all': ('admin/css/company_form.css',)
        }
        js = ('admin/js/company_form.js',)


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    list_display = ('name', 'tax_id', 'city', 'user')
    search_fields = ('name', 'tax_id')
    exclude = ('user',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

@admin.register(MonthlySettlement)
class MonthlySettlementAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/monthlysettlement/change_list.html"
    list_display = ('year', 'month', 'total_revenue', 'income_tax_payable', 'user')
    list_filter = ('year', 'user')
    exclude = ('user',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('oblicz/', self.admin_site.admin_view(self.calculate_view),
                 name='ksiegowosc_monthlysettlement_calculate')
        ]
        return my_urls + urls

    def calculate_view(self, request):
        context = {
            'opts': self.model._meta,
            'site_header': 'Fakturownia',
            'site_title': 'Panel Admina',
            'title': 'Obliczanie Rozliczenia Miesięcznego'
        }

        if request.method == 'POST':
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))
            health_insurance_paid = float(request.POST.get('health_insurance_paid', '0').replace(',', '.'))

            total_revenue = Invoice.objects.filter(
                user=request.user,
                issue_date__year=year,
                issue_date__month=month
            ).aggregate(total=Sum('total_amount'))['total'] or 0.00

            tax_base = float(total_revenue) - (health_insurance_paid * 0.5)
            if tax_base < 0:
                tax_base = 0
            income_tax_payable = round(tax_base * 0.14)

            settlement, _ = MonthlySettlement.objects.update_or_create(
                user=request.user,
                year=year,
                month=month,
                defaults={
                    'total_revenue': total_revenue,
                    'health_insurance_paid': health_insurance_paid,
                    'income_tax_payable': income_tax_payable
                }
            )
            context.update({'settlement': settlement, 'submitted': True})

        current_year = datetime.now().year
        context.update({
            'years': range(current_year - 5, current_year + 1),
            'months': range(1, 13)
        })
        return render(request, 'ksiegowosc/settlement_form.html', context)

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ('total_price',)
    exclude = ('user',)

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]
    list_display = ('invoice_number', 'contractor', 'issue_date', 'total_amount', 'is_correction', 'user')
    list_filter = ('issue_date', 'contractor', 'is_correction', 'user')
    search_fields = ('invoice_number', 'contractor__name')
    exclude = ('user',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "contractor" and not request.user.is_superuser:
            kwargs["queryset"] = Contractor.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not hasattr(instance, 'user') or not instance.user:
                instance.user = request.user
            instance.save()
        formset.save_m2m()

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:object_id>/change/generate-pdf/',
                 self.admin_site.admin_view(self.generate_pdf_view),
                 name='ksiegowosc_invoice_pdf'),
            path('import-jpk/',
                 self.admin_site.admin_view(self.import_jpk_view),
                 name='ksiegowosc_invoice_import_jpk'),
            path('export-jpk/',
                 self.admin_site.admin_view(self.export_jpk_view),
                 name='ksiegowosc_invoice_export_jpk'),
        ]
        return my_urls + urls

    def import_jpk_view(self, request):
        """Import faktur z pozycjami z JPK"""
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            title='Import faktur z JPK_FA',
            has_view_permission=self.has_view_permission(request),
            has_add_permission=self.has_add_permission(request),
            has_change_permission=self.has_change_permission(request),
            has_delete_permission=self.has_delete_permission(request),
        )

        if request.method == 'POST' and request.FILES.get('xml_file'):
            xml_file = request.FILES['xml_file']

            try:
                if xml_file.size > 50 * 1024 * 1024:
                    messages.error(request, "Plik za duży (max 50MB)")
                    return render(request, 'admin/ksiegowosc/invoice/import_jpk.html', context)

                if not xml_file.name.lower().endswith('.xml'):
                    messages.error(request, "Nieprawidłowe rozszerzenie pliku")
                    return render(request, 'admin/ksiegowosc/invoice/import_jpk.html', context)

                with transaction.atomic():
                    created_invoices, skipped_invoices = self.parse_jpk_file(xml_file, request.user)

                if created_invoices:
                    total_invoices = len(created_invoices)
                    total_items = sum(items_count for invoice, items_count in created_invoices)
                    messages.success(request, f"Pomyślnie zaimportowano {total_invoices} faktur z {total_items} pozycjami")

                if skipped_invoices:
                    for skip_msg in skipped_invoices[:5]:
                        messages.warning(request, skip_msg)
                    if len(skipped_invoices) > 5:
                        messages.warning(request, f"...i {len(skipped_invoices) - 5} innych problemów")

                if created_invoices:
                    return redirect('admin:ksiegowosc_invoice_changelist')

            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                import traceback
                traceback.print_exc()
                messages.error(request, f"Nieoczekiwany błąd: {str(e)}")

        return render(request, 'admin/ksiegowosc/invoice/import_jpk.html', context)

    def export_jpk_view(self, request):
        """Eksport faktur z pozycjami do CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="faktury_z_pozycjami.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Numer faktury', 'Data wystawienia', 'Data sprzedaży', 'Kontrahent', 'NIP',
            'Kwota całkowita', 'Sposób płatności', 'Korekta', 'Powód korekty', 'Faktura korygowana',
            'Pozycja 1 - Nazwa', 'Pozycja 1 - Ilość', 'Pozycja 1 - Jednostka', 'Pozycja 1 - Cena', 'Pozycja 1 - Wartość',
            'Pozycja 2 - Nazwa', 'Pozycja 2 - Ilość', 'Pozycja 2 - Jednostka', 'Pozycja 2 - Cena', 'Pozycja 2 - Wartość',
            'Pozycja 3 - Nazwa', 'Pozycja 3 - Ilość', 'Pozycja 3 - Jednostka', 'Pozycja 3 - Cena', 'Pozycja 3 - Wartość'
        ])

        queryset = self.get_queryset(request)
        for invoice in queryset:
            items = list(invoice.items.all())

            row = [
                invoice.invoice_number,
                invoice.issue_date.strftime('%Y-%m-%d'),
                invoice.sale_date.strftime('%Y-%m-%d'),
                invoice.contractor.name,
                invoice.contractor.tax_id,
                str(invoice.total_amount),
                invoice.get_payment_method_display(),
                'Tak' if invoice.is_correction else 'Nie',
                invoice.correction_reason or '',
                invoice.corrected_invoice.invoice_number if invoice.corrected_invoice else '',
            ]

            # Dodaj pozycje (maksymalnie 3)
            for i in range(3):
                if i < len(items):
                    item = items[i]
                    row.extend([
                        item.name,
                        str(item.quantity),
                        item.unit,
                        str(item.unit_price),
                        str(item.total_price)
                    ])
                else:
                    row.extend(['', '', '', '', ''])

            writer.writerow(row)

        return response

    def parse_jpk_file(self, xml_file, user):
        """Parsuje plik JPK i tworzy faktury z pozycjami"""
        try:
            xml_content = xml_file.read()
            if isinstance(xml_content, bytes):
                try:
                    xml_content = xml_content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        xml_content = xml_content.decode('windows-1250')
                    except UnicodeDecodeError:
                        xml_content = xml_content.decode('iso-8859-2')

            if 'JPK' not in xml_content and 'Faktura' not in xml_content:
                raise ValueError("Plik nie zawiera danych JPK_FA")

            root = ET.fromstring(xml_content)

            namespaces = [
                {'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/'},
                {'tns': 'http://jpk.mf.gov.pl/wzor/2021/03/09/03091/'},
                {'tns': 'http://jpk.mf.gov.pl/wzor/2020/03/09/03091/'},
                {'': ''}
            ]

            faktury_nodes = []
            ns = None

            for test_ns in namespaces:
                if 'tns' in test_ns:
                    faktury_nodes = root.findall('tns:Faktura', test_ns)
                else:
                    faktury_nodes = root.findall('.//Faktura')

                if faktury_nodes:
                    ns = test_ns
                    break

            if not faktury_nodes:
                raise ValueError("Nie znaleziono elementów 'Faktura' w pliku JPK")

            # Pobierz wszystkie wiersze faktur z całego dokumentu
            all_invoice_items = self.collect_all_invoice_items(root, ns)

            return self.process_faktury_nodes(faktury_nodes, ns, user, all_invoice_items)

        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}")

    def collect_all_invoice_items(self, root, ns):
        """Zbiera wszystkie pozycje faktur z dokumentu"""
        all_items = {}

        def get_text(node, paths):
            if not isinstance(paths, list):
                paths = [paths]

            for path in paths:
                if 'tns' in ns and ns['tns']:
                    found_node = node.find(f'tns:{path}', ns)
                else:
                    found_node = node.find(path)

                if found_node is not None and found_node.text:
                    return found_node.text.strip()
            return None

        # Szukaj FakturaWiersz na głównym poziomie
        if 'tns' in ns and ns['tns']:
            item_nodes = root.findall('tns:FakturaWiersz', ns)
        else:
            item_nodes = root.findall('.//FakturaWiersz')

        for item_node in item_nodes:
            invoice_number = get_text(item_node, ['P_2B', '2B'])
            if invoice_number:
                if invoice_number not in all_items:
                    all_items[invoice_number] = []

                item_data = {
                    'name': get_text(item_node, ['P_7', '7']) or 'Usługa',
                    'unit': get_text(item_node, ['P_8A', '8A']) or 'szt.',
                    'quantity': get_text(item_node, ['P_8B', '8B']) or '1.00',
                    'unit_price': get_text(item_node, ['P_9B', '9B']) or '0.00',
                    'total_price': get_text(item_node, ['P_11A', '11A']) or '0.00'
                }
                all_items[invoice_number].append(item_data)

        return all_items

    def process_faktury_nodes(self, faktury_nodes, ns, user, all_invoice_items):
        """Przetwarza węzły faktur z XML wraz z pozycjami"""
        def get_text(node, paths):
            if not isinstance(paths, list):
                paths = [paths]

            for path in paths:
                if 'tns' in ns and ns['tns']:
                    found_node = node.find(f'tns:{path}', ns)
                else:
                    found_node = node.find(path)

                if found_node is not None and found_node.text:
                    return found_node.text.strip()
            return None

        def parse_date(date_str):
            if not date_str:
                return datetime.now().date()
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try:
                    return datetime.strptime(date_str, '%d-%m-%Y').date()
                except ValueError:
                    return datetime.now().date()

        def parse_decimal(value_str):
            if not value_str:
                return Decimal('0.00')
            try:
                cleaned_value = value_str.replace(',', '.').replace(' ', '')
                return Decimal(cleaned_value)
            except (InvalidOperation, ValueError):
                return Decimal('0.00')

        created_invoices = []
        skipped_invoices = []

        for faktura_node in faktury_nodes:
            try:
                # Pobierz dane faktury
                invoice_number = get_text(faktura_node, ['P_2A', '2A', 'NrFaktury'])
                buyer_nip = get_text(faktura_node, ['P_5B', '5B', 'NIP'])
                buyer_name = get_text(faktura_node, ['P_3A', '3A', 'Nazwa'])
                issue_date_str = get_text(faktura_node, ['P_1', '1', 'DataWystawienia'])
                sale_date_str = get_text(faktura_node, ['P_6', '6', 'DataSprzedazy'])
                total_amount_str = get_text(faktura_node, ['P_15', '15', 'WartoscBrutto'])

                if not invoice_number or not buyer_nip:
                    skipped_invoices.append(f"Pominięto fakturę - brak numeru lub NIP")
                    continue

                # Sprawdź czy faktura już istnieje
                if Invoice.objects.filter(invoice_number=invoice_number).exists():
                    skipped_invoices.append(f"Faktura {invoice_number} już istnieje")
                    continue

                # Parsuj daty i kwotę
                issue_date = parse_date(issue_date_str)
                sale_date = parse_date(sale_date_str)
                total_amount = parse_decimal(total_amount_str)

                # Sprawdź czy to korekta
                is_correction = False
                correction_reason = None
                corrected_invoice = None

                rodzaj_node = faktura_node.find('tns:RodzajFaktury' if 'tns' in ns else 'RodzajFaktury', ns)
                if rodzaj_node is not None and rodzaj_node.text:
                    is_correction = 'KOREKTA' in rodzaj_node.text.upper()

                # Jeśli to korekta, szukaj dodatkowych informacji
                if is_correction:
                    # POPRAWIONE: Dodaj wszystkie możliwe nazwy pól dla powodu korekty
                    correction_reason = get_text(faktura_node, [
                        'PrzyczynaKorekty', 'tns:PrzyczynaKorekty',
                        'P_16', 'tns:P_16', 'PowodKorekty', 'tns:PowodKorekty',
                        'P_15A', 'tns:P_15A', 'OpisKorekty', 'tns:OpisKorekty',
                        'UwagiKorekta', 'tns:UwagiKorekta', 'Uwagi', 'tns:Uwagi'
                    ])

                    # Domyślny powód jeśli nic nie znaleziono
                    if not correction_reason:
                        correction_reason = "Korekta faktury"

                    print(f"Powód korekty dla {invoice_number}: {correction_reason}")

                    # Numer faktury korygowanej
                    corrected_invoice_number = get_text(faktura_node, [
                        'NrFaKorygowanej', 'tns:NrFaKorygowanej',
                        'P_2B', 'tns:P_2B', 'NrFakturyKorygowanej', 'tns:NrFakturyKorygowanej',
                        'P_2A_Kor', 'tns:P_2A_Kor', 'FakturaKorygowana', 'tns:FakturaKorygowana'
                    ])

                    # Spróbuj znaleźć fakturę korygowaną w systemie
                    if corrected_invoice_number:
                        try:
                            corrected_invoice = Invoice.objects.get(
                                invoice_number=corrected_invoice_number,
                                user=user
                            )
                            print(f"Znaleziono fakturę korygowaną: {corrected_invoice_number}")
                        except Invoice.DoesNotExist:
                            # Faktura korygowana nie istnieje - zapisz w powodzie korekty
                            correction_reason += f" (Dotyczy faktury: {corrected_invoice_number})"
                            print(f"Faktura korygowana {corrected_invoice_number} nie istnieje w systemie")

                # Znajdź lub utwórz kontrahenta
                contractor, created = Contractor.objects.get_or_create(
                    tax_id=buyer_nip,
                    user=user,
                    defaults={'name': buyer_name or 'Brak nazwy'}
                )

                # Utwórz fakturę
                invoice = Invoice.objects.create(
                    user=user,
                    invoice_number=invoice_number,
                    issue_date=issue_date,
                    sale_date=sale_date,
                    contractor=contractor,
                    total_amount=total_amount,
                    is_correction=is_correction,
                    correction_reason=correction_reason,
                    corrected_invoice=corrected_invoice,
                    payment_method='przelew'
                )

                # POPRAWIONE: Użyj zebranych pozycji z FakturaWiersz
                items_created = self.create_invoice_items_from_collected_data(
                    invoice, user, all_invoice_items.get(invoice_number, [])
                )

                # Jeśli nie ma pozycji, utwórz domyślną pozycję
                if items_created == 0 and total_amount > 0:
                    InvoiceItem.objects.create(
                        user=user,
                        invoice=invoice,
                        name="Usługi (import z JPK)",
                        quantity=Decimal('1.00'),
                        unit='szt.',
                        unit_price=total_amount,
                        total_price=total_amount
                    )
                    items_created = 1

                created_invoices.append((invoice, items_created))

            except Exception as e:
                skipped_invoices.append(f"Błąd przetwarzania faktury: {str(e)}")
                continue

        return created_invoices, skipped_invoices

    def create_invoice_items_from_collected_data(self, invoice, user, items_data):
        """Tworzy pozycje faktury z zebranych danych"""
        items_created = 0

        def parse_decimal(value_str):
            if not value_str:
                return Decimal('0.00')
            try:
                cleaned_value = value_str.replace(',', '.').replace(' ', '')
                return Decimal(cleaned_value)
            except (InvalidOperation, ValueError):
                return Decimal('0.00')

        for item_data in items_data:
            try:
                quantity = parse_decimal(item_data['quantity'])
                unit_price = parse_decimal(item_data['unit_price'])
                total_price = parse_decimal(item_data['total_price'])

                # Jeśli brak total_price, oblicz z quantity * unit_price
                if total_price == 0 and quantity > 0 and unit_price > 0:
                    total_price = quantity * unit_price

                # Jeśli brak unit_price ale jest total_price i quantity
                if unit_price == 0 and total_price > 0 and quantity > 0:
                    unit_price = total_price / quantity

                # Jeśli nadal brak danych, zastąp wartości domyślne
                if quantity == 0:
                    quantity = Decimal('1.00')
                if total_price == 0:
                    total_price = unit_price

                InvoiceItem.objects.create(
                    user=user,
                    invoice=invoice,
                    name=item_data['name'] or 'Usługa',
                    quantity=quantity,
                    unit=item_data['unit'] or 'szt.',
                    unit_price=unit_price,
                    total_price=total_price
                )
                items_created += 1

            except Exception as e:
                print(f"Błąd tworzenia pozycji faktury: {str(e)}")
                continue

        return items_created

    def generate_pdf_view(self, request, object_id):
        queryset = self.get_queryset(request)
        try:
            invoice = queryset.get(pk=object_id)
        except Invoice.DoesNotExist:
            messages.error(request, "Faktura nie została znaleziona lub nie masz do niej uprawnień.")
            return redirect(request.META.get('HTTP_REFERER', '/admin/'))

        company_info = CompanyInfo.objects.filter(user=request.user).first()
        if not company_info:
            messages.error(request, "Nie można wygenerować PDF. Uzupełnij najpierw dane firmy w panelu.")
            return redirect(request.META.get('HTTP_REFERER', '/admin/'))

        html_string = render_to_string('ksiegowosc/invoice_pdf_template.html', {
            'invoice': invoice,
            'company_info': company_info
        })
        html = HTML(string=html_string)
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="faktura-{invoice.invoice_number.replace("/", "_")}.pdf"'
        return response

# InvoiceItem nie jest rejestrowany w admin - tylko jako inline w Invoice
