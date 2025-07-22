from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import CompanyInfo, Contractor, Invoice, InvoiceItem, MonthlySettlement
from django.contrib import messages
from django.db.models import Sum, Min, Max
from datetime import datetime
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'tax_id', 'business_type', 'user')
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
                'kod_urzedu',
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

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('oblicz/', self.admin_site.admin_view(self.calculate_view), name='ksiegowosc_monthlysettlement_calculate'),
        ]
        return my_urls + urls

    def calculate_view(self, request):
        context = {
            'opts': self.model._meta, 'title': 'Obliczanie Rozliczenia Miesięcznego',
        }

        if request.method == 'POST':
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))

            health_insurance = Decimal(request.POST.get('health_insurance_paid', '0').replace(',', '.'))
            social_insurance = Decimal(request.POST.get('social_insurance_paid', '0').replace(',', '.'))
            labor_fund = Decimal(request.POST.get('labor_fund_paid', '0').replace(',', '.'))

            total_revenue = Invoice.objects.filter(
                user=request.user, issue_date__year=year, issue_date__month=month
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

            tax_base_revenue = total_revenue - social_insurance
            tax_base_after_health = tax_base_revenue - (health_insurance / 2)
            if tax_base_after_health < 0:
                tax_base_after_health = 0

            income_tax_payable = round(tax_base_after_health * Decimal('0.14'))

            settlement, _ = MonthlySettlement.objects.update_or_create(
                user=request.user, year=year, month=month,
                defaults={
                    'total_revenue': total_revenue,
                    'health_insurance_paid': health_insurance,
                    'social_insurance_paid': social_insurance,
                    'labor_fund_paid': labor_fund,
                    'income_tax_payable': income_tax_payable
                }
            )
            context['settlement'] = settlement
            context['submitted'] = True

        current_year = datetime.now().year
        context.update({'years': range(current_year - 5, current_year + 1), 'months': range(1, 13)})
        return render(request, 'ksiegowosc/settlement_form.html', context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fieldsets = (
        (None, {
            'fields': (
                'corrected_item',
                ('name', 'quantity', 'unit'),
                ('unit_price', 'total_price', 'lump_sum_tax_rate'),
            ),
        }),
    )
    readonly_fields = ('total_price',)
    exclude = ('user',)
    verbose_name = "Pozycja 'powinno być' (po korekcie)"
    verbose_name_plural = "Pozycje 'powinno być' (po korekcie)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "corrected_item":
            try:
                invoice_id = request.resolver_match.kwargs.get('object_id')
                invoice = Invoice.objects.get(pk=invoice_id)
                if invoice.corrected_invoice:
                    kwargs["queryset"] = InvoiceItem.objects.filter(invoice=invoice.corrected_invoice)
                else:
                    kwargs["queryset"] = InvoiceItem.objects.none()
            except (Invoice.DoesNotExist, AttributeError):
                kwargs["queryset"] = InvoiceItem.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]
    list_display = ('invoice_number', 'contractor', 'issue_date', 'total_amount', 'is_correction', 'user')
    list_filter = ('issue_date', 'contractor', 'is_correction', 'user')
    search_fields = ('invoice_number', 'contractor__name')
    exclude = ('user',)
    actions = ['export_selected_to_jpk']

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }

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
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            title='Import faktur z JPK_FA',
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
                    created_invoices, import_warnings = self.parse_jpk_file(xml_file, request.user)
                if created_invoices:
                    messages.success(request, f"Pomyślnie zaimportowano {len(created_invoices)} faktur.")
                    if any(inv.is_correction for inv, _ in created_invoices):
                        messages.warning(request, "IMPORT KOREKTY: Automatycznie powiązano pozycje. Prosimy o weryfikację poprawności w edytorze faktury.")
                else:
                    messages.info(request, "Nie zaimportowano żadnych nowych faktur.")
                if import_warnings:
                    context['import_warnings'] = import_warnings

            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Nieoczekiwany błąd: {str(e)}")

        return render(request, 'admin/ksiegowosc/invoice/import_jpk.html', context)

    def export_jpk_view(self, request):
        selected_ids_str = request.GET.get('ids')
        if not selected_ids_str:
            self.message_user(request, "Nie zaznaczono żadnych faktur do eksportu.", level=messages.WARNING)
            return redirect("admin:ksiegowosc_invoice_changelist")

        selected_ids = selected_ids_str.split(',')
        queryset = self.get_queryset(request).filter(pk__in=selected_ids)

        if not queryset.exists():
            self.message_user(request, "Wybrane faktury nie zostały znalezione.", level=messages.ERROR)
            return redirect("admin:ksiegowosc_invoice_changelist")

        response = HttpResponse(content_type='application/xml; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="jpk_fa_wybrane_{datetime.now().strftime("%Y_%m_%d")}.xml"'

        try:
            company_info = CompanyInfo.objects.get(user=request.user)
        except CompanyInfo.DoesNotExist:
            self.message_user(request, "Brak danych firmy. Uzupełnij je w pierwszej kolejności.", level=messages.ERROR)
            return redirect("admin:ksiegowosc_invoice_changelist")

        ns = {
            'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/',
            'etd': 'http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/'
        }
        ET.register_namespace('tns', ns['tns'])
        ET.register_namespace('etd', ns['etd'])
        root = ET.Element(f"{{{ns['tns']}}}JPK")

        daty = queryset.aggregate(min_date=Min('issue_date'), max_date=Max('issue_date'))
        data_od = daty['min_date'].strftime('%Y-%m-%d') if daty['min_date'] else ''
        data_do = daty['max_date'].strftime('%Y-%m-%d') if daty['max_date'] else ''

        header = ET.SubElement(root, f"{{{ns['tns']}}}Naglowek")
        ET.SubElement(header, f"{{{ns['tns']}}}KodFormularza", attrib={"kodSystemowy": "JPK_FA (4)", "wersjaSchemy": "1-0"}).text = "JPK_FA"
        ET.SubElement(header, f"{{{ns['tns']}}}WariantFormularza").text = "4"
        ET.SubElement(header, f"{{{ns['tns']}}}DataWytworzeniaJPK").text = datetime.now().isoformat()
        if data_od and data_do:
             ET.SubElement(header, f"{{{ns['tns']}}}DataOd").text = data_od
             ET.SubElement(header, f"{{{ns['tns']}}}DataDo").text = data_do
        ET.SubElement(header, f"{{{ns['tns']}}}NazwaSystemu").text = "Fakturownia App"
        ET.SubElement(header, f"{{{ns['tns']}}}CelZlozenia").text = "1"
        ET.SubElement(header, f"{{{ns['tns']}}}KodUrzędu").text = company_info.kod_urzedu or ""

        podmiot = ET.SubElement(root, f"{{{ns['tns']}}}Podmiot1")
        identyfikator = ET.SubElement(podmiot, f"{{{ns['tns']}}}IdentyfikatorPodmiotu")
        ET.SubElement(identyfikator, f"{{{ns['tns']}}}NIP").text = company_info.tax_id.replace("-", "")
        ET.SubElement(identyfikator, f"{{{ns['tns']}}}PelnaNazwa").text = company_info.company_name
        adres_podmiotu = ET.SubElement(podmiot, f"{{{ns['tns']}}}AdresPodmiotu")
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}KodKraju").text = "PL"
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Wojewodztwo").text = company_info.voivodeship or ""
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Ulica").text = company_info.street or ""
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Miejscowosc").text = company_info.city or ""
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}KodPocztowy").text = company_info.zip_code or ""

        for invoice in queryset:
            faktura = ET.SubElement(root, f"{{{ns['tns']}}}Faktura", attrib={"typ": "G"})
            ET.SubElement(faktura, f"{{{ns['tns']}}}KodWaluty").text = "PLN"
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_1").text = invoice.issue_date.strftime('%Y-%m-%d')
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_2A").text = invoice.invoice_number
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_3A").text = invoice.contractor.name
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_3B").text = f"{invoice.contractor.street}, {invoice.contractor.zip_code} {invoice.contractor.city}"
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_3C").text = company_info.company_name
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_3D").text = company_info.get_full_address()
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_4B").text = company_info.tax_id.replace("-", "")
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_5B").text = invoice.contractor.tax_id.replace("-", "")
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_6").text = invoice.sale_date.strftime('%Y-%m-%d')
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_13_7").text = str(invoice.total_amount)
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_15").text = str(invoice.total_amount)

            if invoice.is_correction:
                ET.SubElement(faktura, f"{{{ns['tns']}}}RodzajFaktury").text = "KOREKTA"
                ET.SubElement(faktura, f"{{{ns['tns']}}}PrzyczynaKorekty").text = invoice.correction_reason
                if invoice.corrected_invoice:
                    ET.SubElement(faktura, f"{{{ns['tns']}}}NrFaKorygowanej").text = invoice.corrected_invoice.invoice_number
            else:
                ET.SubElement(faktura, f"{{{ns['tns']}}}RodzajFaktury").text = "VAT"

            for item in invoice.items.all():
                wiersz = ET.SubElement(root, f"{{{ns['tns']}}}FakturaWiersz")
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_2B").text = invoice.invoice_number
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_7").text = item.name
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_8A").text = str(item.quantity)
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_8B").text = item.unit
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_9A").text = str(item.unit_price)
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_11").text = str(item.total_price)
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_12").text = "zw"

        tree = ET.ElementTree(root)
        ET.indent(tree, space="\t", level=0)
        tree.write(response, encoding='utf-8', xml_declaration=True)
        return response

    def parse_jpk_file(self, xml_file, user):
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
            all_invoice_items = self.collect_all_invoice_items(root, ns)
            return self.process_faktury_nodes(faktury_nodes, ns, user, all_invoice_items)
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}")

    def collect_all_invoice_items(self, root, ns):
        all_items = {}
        def get_text(node, paths):
            if not isinstance(paths, list): paths = [paths]
            for path in paths:
                if 'tns' in ns and ns['tns']: found_node = node.find(f'tns:{path}', ns)
                else: found_node = node.find(path)
                if found_node is not None and found_node.text: return found_node.text.strip()
            return None
        if 'tns' in ns and ns['tns']: item_nodes = root.findall('tns:FakturaWiersz', ns)
        else: item_nodes = root.findall('.//FakturaWiersz')
        for item_node in item_nodes:
            invoice_number = get_text(item_node, ['P_2B', '2B'])
            if invoice_number:
                if invoice_number not in all_items: all_items[invoice_number] = []
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
        def get_text(node, paths):
            if not isinstance(paths, list): paths = [paths]
            for path in paths:
                if 'tns' in ns and ns['tns']: found_node = node.find(f'tns:{path}', ns)
                else: found_node = node.find(path)
                if found_node is not None and found_node.text: return found_node.text.strip()
            return None
        def parse_date(date_str):
            if not date_str: return datetime.now().date()
            try: return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                try: return datetime.strptime(date_str, '%d-%m-%Y').date()
                except ValueError: return datetime.now().date()
        def parse_decimal(value_str):
            if not value_str: return Decimal('0.00')
            try: return Decimal(value_str.replace(',', '.').replace(' ', ''))
            except (InvalidOperation, ValueError): return Decimal('0.00')

        created_invoices = []
        import_warnings = []
        temp_invoice_counter = 0

        for faktura_node in faktury_nodes:
            try:
                invoice_number = get_text(faktura_node, ['P_2A', '2A', 'NrFaktury'])
                buyer_nip = get_text(faktura_node, ['P_5B', '5B', 'NIP'])
                buyer_name = get_text(faktura_node, ['P_3A', '3A', 'Nazwa'])
                issue_date_str = get_text(faktura_node, ['P_1', '1', 'DataWystawienia'])
                sale_date_str = get_text(faktura_node, ['P_6', '6', 'DataSprzedazy'])
                total_amount_str = get_text(faktura_node, ['P_15', 'WartoscBrutto'])
                notes_from_jpk = ""

                if not invoice_number:
                    temp_invoice_counter += 1
                    invoice_number = f"TEMP_JPK_{timezone.now().strftime('%Y%m%d%H%M%S')}_{temp_invoice_counter}"
                    notes_from_jpk = "Numer faktury został wygenerowany automatycznie podczas importu JPK."
                    import_warnings.append(f"Faktura bez numeru: nadano tymczasowy numer '{invoice_number}'.")

                if Invoice.objects.filter(invoice_number=invoice_number, user=user).exists():
                    import_warnings.append(f"Pominięto: Faktura o numerze '{invoice_number}' już istnieje w systemie.")
                    continue

                if buyer_nip:
                    contractor, created = Contractor.objects.get_or_create(
                        tax_id=buyer_nip,
                        user=user,
                        defaults={'name': buyer_name or 'Brak nazwy w JPK'}
                    )
                else:
                    if not buyer_name:
                        import_warnings.append(f"Pominięto fakturę (prawdopodobnie '{invoice_number}'): brak NIP i nazwy kontrahenta.")
                        continue
                    contractor, created = Contractor.objects.get_or_create(
                        name=buyer_name, tax_id=None, user=user
                    )
                    if created:
                        import_warnings.append(f"Utworzono nowego kontrahenta '{buyer_name}' bez numeru NIP.")

                issue_date = parse_date(issue_date_str)
                sale_date = parse_date(sale_date_str) if sale_date_str else issue_date
                total_amount = parse_decimal(total_amount_str)
                is_correction = False
                correction_reason = None
                corrected_invoice = None
                original_items = []

                rodzaj_node = faktura_node.find('tns:RodzajFaktury' if 'tns' in ns else 'RodzajFaktury', ns)
                if rodzaj_node is not None and 'KOREKTA' in (rodzaj_node.text or '').upper():
                    is_correction = True
                    correction_reason = get_text(faktura_node, ['PrzyczynaKorekty', 'tns:PrzyczynaKorekty']) or "Korekta faktury"
                    corrected_invoice_number = get_text(faktura_node, ['NrFaKorygowanej', 'tns:NrFaKorygowanej'])
                    if corrected_invoice_number:
                        try:
                            corrected_invoice = Invoice.objects.get(invoice_number=corrected_invoice_number, user=user)
                            original_items = list(corrected_invoice.items.all().order_by('pk'))
                        except Invoice.DoesNotExist:
                            correction_reason += f" (Faktura korygowana {corrected_invoice_number} nie istnieje w systemie)"
                            import_warnings.append(f"Korekta '{invoice_number}': nie znaleziono w bazie faktury korygowanej {corrected_invoice_number}.")

                invoice = Invoice.objects.create(
                    user=user, invoice_number=invoice_number, issue_date=issue_date,
                    sale_date=sale_date, contractor=contractor, total_amount=total_amount,
                    is_correction=is_correction, correction_reason=correction_reason,
                    corrected_invoice=corrected_invoice, payment_method='przelew', notes=notes_from_jpk
                )

                correction_items_data = all_invoice_items.get(invoice_number, [])
                items_created = self.create_invoice_items_from_collected_data(
                    invoice, user, correction_items_data, original_items if is_correction else []
                )

                if items_created == 0 and total_amount > 0:
                    InvoiceItem.objects.create(
                        user=user, invoice=invoice, name="Usługi (import z JPK)",
                        quantity=Decimal('1.00'), unit='szt.', unit_price=total_amount, total_price=total_amount
                    )
                    items_created = 1

                # === OSTATECZNA POPRAWKA ===
                # Nadpisujemy kwotę faktury jeszcze raz, na wypadek gdyby logika modelu ją zmieniła.
                if invoice.total_amount != total_amount:
                    invoice.total_amount = total_amount
                    invoice.save(update_fields=['total_amount'])

                created_invoices.append((invoice, items_created))
            except Exception as e:
                import_warnings.append(f"Błąd krytyczny przy przetwarzaniu faktury: {str(e)}")
                continue
        return created_invoices, import_warnings

    def create_invoice_items_from_collected_data(self, invoice, user, items_data, original_items=None):
        if original_items is None:
            original_items = []
        items_created = 0
        def parse_decimal(value_str):
            if not value_str: return Decimal('0.00')
            try: return Decimal(value_str.replace(',', '.').replace(' ', ''))
            except (InvalidOperation, ValueError): return Decimal('0.00')

        for idx, item_data in enumerate(items_data):
            try:
                quantity = parse_decimal(item_data['quantity'])
                unit_price = parse_decimal(item_data['unit_price'])
                total_price = parse_decimal(item_data['total_price'])
                if total_price == 0 and quantity > 0 and unit_price > 0: total_price = quantity * unit_price
                if unit_price == 0 and total_price > 0 and quantity > 0: unit_price = total_price / quantity
                if quantity == 0: quantity = Decimal('1.00')
                if total_price == 0: total_price = unit_price

                new_item = InvoiceItem.objects.create(
                    user=user, invoice=invoice, name=item_data['name'] or 'Usługa',
                    quantity=quantity, unit=item_data['unit'] or 'szt.',
                    unit_price=unit_price, total_price=total_price
                )

                if original_items and idx < len(original_items):
                    new_item.corrected_item = original_items[idx]
                    new_item.save()

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
