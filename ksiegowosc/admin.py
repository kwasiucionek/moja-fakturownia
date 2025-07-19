# ksiegowosc/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import CompanyInfo, Contractor, Invoice, InvoiceItem, MonthlySettlement

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
import base64
import re
import subprocess
from django.db import transaction
from django.db.models import Sum

# --- PANEL ADMINA DLA PROSTYCH MODELI ---

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'tax_id', 'user')
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
            path('oblicz/', self.admin_site.admin_view(self.calculate_view), name='ksiegowosc_monthlysettlement_calculate'),
        ]
        return my_urls + urls

    def calculate_view(self, request):
        context = {
            'site_header': 'Fakturownia', 'site_title': 'Panel Admina',
            'title': 'Obliczanie Rozliczenia Miesięcznego', 'opts': self.model._meta,
        }

        if request.method == 'POST':
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))
            health_insurance_paid_str = request.POST.get('health_insurance_paid', '0').replace(',', '.')
            health_insurance_paid = float(health_insurance_paid_str)

            total_revenue = Invoice.objects.filter(
                user=request.user, issue_date__year=year, issue_date__month=month
            ).aggregate(total=Sum('total_amount'))['total'] or 0.00

            tax_base = float(total_revenue) - (health_insurance_paid * 0.5)
            if tax_base < 0: tax_base = 0

            income_tax_payable = round(tax_base * 0.14)

            settlement, created = MonthlySettlement.objects.update_or_create(
                user=request.user, year=year, month=month,
                defaults={
                    'total_revenue': total_revenue,
                    'health_insurance_paid': health_insurance_paid,
                    'income_tax_payable': income_tax_payable
                }
            )
            context['settlement'] = settlement
            context['submitted'] = True

        current_year = datetime.now().year
        context['years'] = range(current_year - 5, current_year + 1)
        context['months'] = range(1, 13)
        return render(request, 'ksiegowosc/settlement_form.html', context)


# --- WIDOK INLINE DLA POZYCJI FAKTURY ---
class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ('total_price',)
    exclude = ('user',)


# --- ROZBUDOWANY PANEL ADMINA DLA FAKTUR ---
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline]
    list_display = ('invoice_number', 'contractor', 'issue_date', 'total_amount', 'is_correction', 'user')
    list_filter = ('issue_date', 'contractor', 'is_correction', 'user')
    search_fields = ('invoice_number', 'contractor__name')
    exclude = ('user',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "contractor":
            if not request.user.is_superuser:
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
            path('import/', self.admin_site.admin_view(self.import_jpk_fa_view), name='ksiegowosc_invoice_import'),
            path('<int:object_id>/change/generate-pdf/', self.admin_site.admin_view(self.generate_pdf_view), name='ksiegowosc_invoice_pdf'),
        ]
        return my_urls + urls

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

    def import_jpk_fa_view(self, request):
        context = {
            'opts': self.model._meta,
            'site_header': 'Fakturownia',
            'site_title': 'Panel Admina',
            'title': 'Import Faktur z Pliku JPK',
        }

        if request.method == 'POST' and request.FILES.get('xml_file'):
            xml_file = request.FILES['xml_file']
            try:
                ns = {'tns': 'http://jpk.mf.gov.pl/wzor/2022/02/17/02171/'}
                tree = ET.parse(xml_file)
                root = tree.getroot()
                invoices_created_count = 0
                all_invoices_in_file = {}
                corrections_to_link = {}

                with transaction.atomic():
                    for faktura_node in root.findall('tns:Faktura', ns):
                        invoice_number = faktura_node.find('tns:P_2A', ns).text
                        nabywca_nip = faktura_node.find('tns:P_5B', ns).text
                        nabywca_name = faktura_node.find('tns:P_3A', ns).text
                        nabywca_address = faktura_node.find('tns:P_3B', ns).text
                        street, zip_code, city = "", "", ""
                        address_parts = nabywca_address.split(',')
                        if len(address_parts) == 2:
                            street = address_parts[0].strip()
                            zip_city_match = re.search(r'(\d{2}-\d{3})\s+(.*)', address_parts[1].strip())
                            if zip_city_match: zip_code, city = zip_city_match.groups()

                        contractor, _ = Contractor.objects.get_or_create(
                            user=request.user, tax_id=nabywca_nip,
                            defaults={'name': nabywca_name, 'street': street, 'zip_code': zip_code, 'city': city}
                        )

                        invoice_defaults = {
                            'user': request.user, 'contractor': contractor,
                            'issue_date': faktura_node.find('tns:P_1', ns).text, 'sale_date': faktura_node.find('tns:P_6', ns).text,
                            'payment_date': faktura_node.find('tns:P_1', ns).text, 'total_amount': faktura_node.find('tns:P_15', ns).text,
                            'is_correction': False, 'correction_reason': None, 'corrected_invoice': None
                        }

                        rodzaj_faktury_node = faktura_node.find('tns:RodzajFaktury', ns)
                        if rodzaj_faktury_node is not None and rodzaj_faktury_node.text == 'KOREKTA':
                            invoice_defaults['is_correction'] = True
                            przyczyna_node = faktura_node.find('tns:PrzyczynaKorekty', ns)
                            if przyczyna_node is not None: invoice_defaults['correction_reason'] = przyczyna_node.text

                        invoice_obj, created = Invoice.objects.update_or_create(
                            invoice_number=invoice_number, user=request.user,
                            defaults=invoice_defaults
                        )

                        all_invoices_in_file[invoice_number] = invoice_obj
                        if created: invoices_created_count += 1

                        if invoice_obj.is_correction:
                            nr_korygowanej_node = faktura_node.find('tns:NrFaKorygowanej', ns)
                            if nr_korygowanej_node is not None: corrections_to_link[invoice_obj] = nr_korygowanej_node.text

                    for correction_invoice, original_invoice_number in corrections_to_link.items():
                        try:
                            original_invoice = Invoice.objects.get(invoice_number=original_invoice_number, user=request.user)
                            correction_invoice.corrected_invoice = original_invoice
                            correction_invoice.save()
                        except Invoice.DoesNotExist: pass

                    InvoiceItem.objects.filter(invoice__invoice_number__in=all_invoices_in_file.keys(), invoice__user=request.user).delete()

                    for wiersz_node in root.findall('tns:FakturaWiersz', ns):
                        invoice_number = wiersz_node.find('tns:P_2B', ns).text
                        invoice = all_invoices_in_file.get(invoice_number)
                        if not invoice: continue

                        if invoice.is_correction:
                            pass # Pozycje korekt dodajemy zbiorczo poniżej
                        else:
                            InvoiceItem.objects.create(
                                invoice=invoice, user=request.user, name=wiersz_node.find('tns:P_7', ns).text,
                                unit_price=Decimal(wiersz_node.find('tns:P_9B', ns).text),
                                quantity=Decimal(wiersz_node.find('tns:P_8B', ns).text),
                                unit=wiersz_node.find('tns:P_8A', ns).text
                            )

                    for invoice_number, invoice in all_invoices_in_file.items():
                        if invoice.is_correction:
                            reason = invoice.correction_reason or "Korekta faktury"
                            original_inv_num = invoice.corrected_invoice.invoice_number if invoice.corrected_invoice else ""
                            item_name = f"{reason} (dot. {original_inv_num})"

                            InvoiceItem.objects.create(
                                invoice=invoice, user=request.user, name=item_name, unit_price=invoice.total_amount,
                                quantity=1, unit="szt."
                            )

                messages.success(request, f"Import zakończony. Utworzono {invoices_created_count} nowych faktur i zaktualizowano dane.")
            except Exception as e:
                messages.error(request, f"Wystąpił nieoczekiwany błąd: {e}")

            return redirect("admin:ksiegowosc_invoice_changelist")

        return render(request, "admin/ksiegowosc/invoice/import_form.html", context)
