# ksiegowosc/admin.py

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, F, Max, Min, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# Import usług KSeF
from ksef.services import send_invoice_to_ksef
from weasyprint import HTML

from .models import (
    CompanyInfo,
    Contractor,
    DutyRate,
    DutyShift,
    ExpenseCategory,
    Invoice,
    InvoiceItem,
    MonthlySettlement,
    Payment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    YearlySettlement,
    ZUSRates,
)

DNI_TYGODNIA_PL = [
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
]

# ==== CUSTOM FILTER DLA STATUSU PŁATNOŚCI ====


class PaymentStatusFilter(admin.SimpleListFilter):
    title = "Status płatności"
    parameter_name = "payment_status"

    def lookups(self, request, model_admin):
        return (
            ("paid", "Opłacone"),
            ("partial", "Częściowo opłacone"),
            ("overdue", "Przeterminowane"),
            ("unpaid", "Nieopłacone"),
        )

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == "paid":
            return (
                queryset.annotate(paid_sum=Sum("payments__amount"))
                .filter(paid_sum__gte=F("total_amount"))
                .distinct()
            )

        elif self.value() == "partial":
            return (
                queryset.annotate(paid_sum=Sum("payments__amount"))
                .filter(paid_sum__gt=0, paid_sum__lt=F("total_amount"))
                .distinct()
            )

        elif self.value() == "overdue":
            return (
                queryset.filter(payment_date__lt=today)
                .annotate(paid_sum=Sum("payments__amount"))
                .exclude(paid_sum__gte=F("total_amount"))
                .distinct()
            )

        elif self.value() == "unpaid":
            return queryset.filter(payments__isnull=True).distinct()

        return queryset


# ==== COMPANY INFO ADMIN ====


@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ("company_name", "tax_id", "business_type", "user")
    list_filter = (
        "business_type",
        "income_tax_type",
        "vat_settlement",
        "vat_payer",
        "zus_payer",
    )
    search_fields = ("company_name", "tax_id", "regon", "krs")
    exclude = ("user",)

    fieldsets = (
        (
            "Dane identyfikacyjne",
            {
                "fields": (
                    "company_name",
                    "short_name",
                    "business_type",
                    "tax_id",
                    "regon",
                    "krs",
                    "pkd_code",
                    "pkd_description",
                )
            },
        ),
        ("Adres", {"fields": ("street", "zip_code", "city", "voivodeship", "country")}),
        ("Dane kontaktowe", {"fields": ("phone", "fax", "email", "website")}),
        (
            "Rachunek bankowy",
            {"fields": ("bank_account_number", "bank_name", "bank_swift")},
        ),
        (
            "Podatki dochodowe",
            {
                "fields": (
                    "income_tax_type",
                    "kod_urzedu",
                    "lump_sum_rate",
                    "business_start_date",
                    "tax_year_start",
                ),
                "description": "Ustawienia dotyczące podatku dochodowego od osób fizycznych lub prawnych",
            },
        ),
        (
            "Podatek od towarów i usług VAT",
            {
                "fields": (
                    "vat_payer",
                    "vat_settlement",
                    "vat_id",
                    "vat_cash_method",
                    "small_taxpayer_vat",
                ),
                "description": "Ustawienia dotyczące podatku VAT",
            },
        ),
        (
            "Rozliczenia z Zakładem Ubezpieczeń Społecznych",
            {
                "fields": (
                    "zus_payer",
                    "zus_number",
                    "zus_code",
                    "preferential_zus",
                    "small_zus_plus",
                    "small_zus_plus_base",
                    "zus_health_insurance_only",
                    "zus_start_relief",
                    "zus_sickness_insurance",
                ),
                "description": "Ustawienia dotyczące składek ZUS",
            },
        ),
        (
            "Księgowość i ewidencja",
            {
                "fields": (
                    "accounting_method",
                    "electronic_invoices",
                    "jpk_fa_required",
                ),
                "description": "Ustawienia dotyczące prowadzenia ewidencji księgowej",
            },
        ),
        (
            "Konfiguracja KSeF",
            {
                "fields": ("ksef_token", "ksef_environment"),
                "description": "Dane dostępowe do systemów Ministerstwa Finansów",
            },
        ),
        (
            "Przedstawiciel ustawowy",
            {
                "fields": (
                    "legal_representative_name",
                    "legal_representative_position",
                ),
                "classes": ("collapse",),
                "description": "Dane przedstawiciela ustawowego (dla spółek)",
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== CONTRACTOR ADMIN ====


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    list_display = ("name", "tax_id", "city", "user")
    search_fields = ("name", "tax_id")
    exclude = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== PAYMENT ADMIN ====


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "contractor_name",
        "amount",
        "payment_date",
        "payment_method",
        "status",
        "user",
    )
    list_filter = ("payment_method", "status", "payment_date", "user")
    search_fields = (
        "invoice__invoice_number",
        "invoice__contractor__name",
        "bank_reference",
    )
    exclude = ("user",)
    autocomplete_fields = ["invoice"]

    def invoice_number(self, obj):
        return obj.invoice.invoice_number

    invoice_number.short_description = "Numer faktury"
    invoice_number.admin_order_field = "invoice__invoice_number"

    def contractor_name(self, obj):
        return obj.invoice.contractor.name

    contractor_name.short_description = "Kontrahent"
    contractor_name.admin_order_field = "invoice__contractor__name"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "invoice" and not request.user.is_superuser:
            kwargs["queryset"] = Invoice.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== INLINES ====


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "corrected_item",
                    ("name", "quantity", "unit"),
                    ("unit_price", "total_price", "lump_sum_tax_rate"),
                ),
            },
        ),
    )
    readonly_fields = ("total_price",)
    exclude = ("user",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "corrected_item":
            try:
                invoice_id = request.resolver_match.kwargs.get("object_id")
                invoice = Invoice.objects.get(pk=invoice_id)
                if invoice.corrected_invoice:
                    kwargs["queryset"] = InvoiceItem.objects.filter(
                        invoice=invoice.corrected_invoice
                    )
                else:
                    kwargs["queryset"] = InvoiceItem.objects.none()
            except (Invoice.DoesNotExist, AttributeError):
                kwargs["queryset"] = InvoiceItem.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    exclude = ("user",)
    fields = (
        "amount",
        "payment_date",
        "payment_method",
        "bank_reference",
        "status",
        "notes",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)


# ==== INVOICE ADMIN ====


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/invoice/change_list.html"
    inlines = [InvoiceItemInline, PaymentInline]
    list_display = (
        "invoice_number",
        "contractor",
        "issue_date",
        "total_amount",
        "payment_status_colored",
        "ksef_status_display",
        "duty_annex_link",
        "user",
    )
    list_filter = (
        "issue_date",
        "contractor",
        "is_correction",
        "user",
        PaymentStatusFilter,
        "ksef_status",
    )
    search_fields = ("invoice_number", "contractor__name")
    exclude = ("user",)
    actions = ["export_selected_to_jpk", "reset_ksef_status_action"]

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}

    def ksef_status_display(self, obj):
        colors = {
            "draft": "gray",
            "pending": "orange",
            "success": "green",
            "error": "red",
        }
        status_name = dict(obj._meta.get_field("ksef_status").choices).get(
            obj.ksef_status, "Nieznany"
        )
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.ksef_status, "black"),
            status_name,
        )

    ksef_status_display.short_description = "Status KSeF"

    def payment_status_colored(self, obj):
        status = obj.payment_status
        colors = {
            "paid": "green",
            "partial": "orange",
            "overdue": "red",
            "unpaid": "gray",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(status, "black"),
            obj.payment_status_display,
        )

    payment_status_colored.short_description = "Status płatności"

    def balance_due_colored(self, obj):
        balance = obj.balance_due
        if balance <= 0:
            return mark_safe(
                '<span style="color: green; font-weight: bold;">0.00 PLN</span>'
            )
        elif obj.is_overdue:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} PLN</span>', balance
            )
        else:
            return format_html('<span style="color: orange;">{} PLN</span>', balance)

    balance_due_colored.short_description = "Do zapłaty"

    def duty_annex_link(self, obj):
        if not obj.duty_shifts.exists():
            return "—"
        url = reverse("admin:ksiegowosc_dutyshift_annex_pdf") + f"?invoice_id={obj.id}"
        return format_html('<a href="{}" target="_blank">załącznik (dyżury)</a>', url)

    duty_annex_link.short_description = "Załącznik do faktury"

    @admin.action(description="Resetuj status KSeF dla zaznaczonych")
    def reset_ksef_status_action(self, request, queryset):
        """Umożliwia ręczne przywrócenie statusu draft dla wybranych faktur"""
        count = queryset.update(
            ksef_status="draft",
            ksef_number=None,
            ksef_reference_number=None,
            ksef_session_id=None,
            ksef_processing_description="Status zresetowany ręcznie przez administratora."
        )
        self.message_user(request, f"Zresetowano status KSeF dla {count} faktur.")

    def import_ksef_sales_view(self, request):
        from ksef.ksef2_import import import_sales_invoices_from_ksef

        try:
            company_info = CompanyInfo.objects.get(user=request.user)
        except CompanyInfo.DoesNotExist:
            messages.error(request, "Uzupełnij najpierw dane firmy (CompanyInfo) i token KSeF.")
            return redirect("admin:ksiegowosc_invoice_changelist")

        if request.method == "POST":
            try:
                days = int(request.POST.get("days", 30))
            except (TypeError, ValueError):
                days = 30

            result = import_sales_invoices_from_ksef(company_info, days=days)

            if result.created:
                messages.success(request, f"Utworzono {result.created} nowych faktur na podstawie KSeF.")
            if result.synced:
                messages.info(request, f"Zsynchronizowano status KSeF na {result.synced} istniejących fakturach.")
            if result.errors:
                for err in result.errors[:10]:
                    messages.warning(request, err)
                if len(result.errors) > 10:
                    messages.warning(request, f"...i {len(result.errors) - 10} więcej błędów.")
            if not result.created and not result.synced and not result.errors:
                messages.info(request, "Brak faktur do zaimportowania/zsynchronizowania w podanym okresie.")

            return redirect("admin:ksiegowosc_invoice_changelist")

        return render(
            request,
            "admin/ksiegowosc/invoice/import_ksef.html",
            {"opts": self.model._meta, "title": "Import/synchronizacja faktur z KSeF", "company_info": company_info},
        )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "import-ksef-sprzedaz/",
                self.admin_site.admin_view(self.import_ksef_sales_view),
                name="ksiegowosc_invoice_import_ksef",
            ),
            path(
                "<int:object_id>/change/generate-pdf/",
                self.admin_site.admin_view(self.generate_pdf_view),
                name="ksiegowosc_invoice_pdf",
            ),
            path(
                "import-jpk/",
                self.admin_site.admin_view(self.import_jpk_view),
                name="ksiegowosc_invoice_import_jpk",
            ),
            path(
                "export-jpk/",
                self.admin_site.admin_view(self.export_jpk_view),
                name="ksiegowosc_invoice_export_jpk",
            ),
            path(
                "send-ksef/",
                self.admin_site.admin_view(self.send_to_ksef_view),
                name="ksiegowosc_invoice_send_ksef",
            ),
            path(
                "payments-report/",
                self.admin_site.admin_view(self.payments_report_view),
                name="ksiegowosc_invoice_payments_report",
            ),
            path(
                "overdue-report/",
                self.admin_site.admin_view(self.overdue_report_view),
                name="ksiegowosc_invoice_overdue_report",
            ),
        ]
        return my_urls + urls

    def send_to_ksef_view(self, request):
        selected_ids_str = request.GET.get('ids')
        if not selected_ids_str:
            messages.warning(request, "Nie zaznaczono żadnych faktur do wysyłki.")
            return redirect("admin:ksiegowosc_invoice_changelist")

        selected_ids = selected_ids_str.split(',')
        queryset = Invoice.objects.filter(pk__in=selected_ids, user=request.user).filter(Q(ksef_status="draft") | Q(ksef_status="error"))

        if not queryset.exists():
            messages.info(request, "Wybrane faktury zostały już wysłane lub są w trakcie przetwarzania.")
            return redirect("admin:ksiegowosc_invoice_changelist")

        for inv in queryset:
            res = send_invoice_to_ksef(inv.id)
            if res['success']:
                messages.success(request, f"Faktura {inv.invoice_number}: {res['message']}")
            else:
                # Ta zmiana pozwoli Ci zobaczyć w alercie np. "Błąd 403: Brak uprawnienia do wystawiania faktur"
                messages.error(request, f"BŁĄD Faktury {inv.invoice_number}: {res['message']}")

        return redirect("admin:ksiegowosc_invoice_changelist")

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
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not hasattr(instance, "user") or not instance.user:
                instance.user = request.user
            instance.save()
        formset.save_m2m()

    def payments_report_view(self, request):
        today = timezone.now().date()
        stats = {
            "total_invoices": Invoice.objects.filter(user=request.user).count(),
            "paid_invoices": Invoice.objects.filter(user=request.user)
            .annotate(paid_sum=Sum("payments__amount"))
            .filter(paid_sum__gte=F("total_amount"))
            .distinct()
            .count(),
            "overdue_invoices": Invoice.objects.filter(
                user=request.user, payment_date__lt=today
            )
            .annotate(paid_sum=Sum("payments__amount"))
            .exclude(paid_sum__gte=F("total_amount"))
            .count(),
            "total_outstanding": Invoice.objects.filter(user=request.user).aggregate(
                total=Sum("total_amount")
            )["total"]
            or 0,
            "total_paid": Payment.objects.filter(
                user=request.user, status="completed"
            ).aggregate(total=Sum("amount"))["total"]
            or 0,
        }
        stats["outstanding_balance"] = stats["total_outstanding"] - stats["total_paid"]
        recent_payments = (
            Payment.objects.filter(user=request.user)
            .select_related("invoice", "invoice__contractor")
            .order_by("-payment_date")[:10]
        )
        overdue_invoices = (
            Invoice.objects.filter(user=request.user, payment_date__lt=today)
            .annotate(paid_sum=Sum("payments__amount"))
            .exclude(paid_sum__gte=F("total_amount"))
            .select_related("contractor")[:10]
        )
        context = {
            "opts": self.model._meta,
            "title": "Raport płatności",
            "stats": stats,
            "recent_payments": recent_payments,
            "overdue_invoices": overdue_invoices,
        }
        return render(request, "admin/ksiegowosc/payment_report.html", context)

    def overdue_report_view(self, request):
        today = timezone.now().date()
        overdue_invoices = (
            Invoice.objects.filter(user=request.user, payment_date__lt=today)
            .annotate(paid_sum=Sum("payments__amount"))
            .exclude(paid_sum__gte=F("total_amount"))
            .select_related("contractor")
            .order_by("payment_date")
        )
        overdue_groups = {
            "group_1_30": [],
            "group_31_60": [],
            "group_61_90": [],
            "group_90_plus": [],
        }
        for invoice in overdue_invoices:
            days_overdue = (today - invoice.payment_date).days
            if days_overdue <= 30:
                overdue_groups["group_1_30"].append(invoice)
            elif days_overdue <= 60:
                overdue_groups["group_31_60"].append(invoice)
            elif days_overdue <= 90:
                overdue_groups["group_61_90"].append(invoice)
            else:
                overdue_groups["group_90_plus"].append(invoice)
        context = {
            "opts": self.model._meta,
            "title": "Przeterminowane płatności",
            "overdue_groups": overdue_groups,
            "total_overdue": len(overdue_invoices),
        }
        return render(request, "admin/ksiegowosc/overdue_report.html", context)

    def import_jpk_view(self, request):
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            title="Import faktur z JPK_FA",
        )
        if request.method == "POST" and request.FILES.get("xml_file"):
            xml_file = request.FILES["xml_file"]
            try:
                if xml_file.size > 50 * 1024 * 1024:
                    messages.error(request, "Plik za duży (max 50MB)")
                    return render(
                        request, "admin/ksiegowosc/invoice/import_jpk.html", context
                    )
                if not xml_file.name.lower().endswith(".xml"):
                    messages.error(request, "Nieprawidłowe rozszerzenie pliku")
                    return render(
                        request, "admin/ksiegowosc/invoice/import_jpk.html", context
                    )
                with transaction.atomic():
                    created_invoices, import_warnings = self.parse_jpk_file(
                        xml_file, request.user
                    )
                if created_invoices:
                    messages.success(
                        request,
                        f"Pomyślnie zaimportowano {len(created_invoices)} faktur.",
                    )
                    if any(inv.is_correction for inv, _ in created_invoices):
                        messages.warning(
                            request,
                            "IMPORT KOREKTY: Automatycznie powiązano pozycje. Prosimy o weryfikację poprawności w edytorze faktury.",
                        )
                else:
                    messages.info(request, "Nie zaimportowano żadnych nowych faktur.")
                if import_warnings:
                    context["import_warnings"] = import_warnings
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Nieoczekiwany błąd: {str(e)}")
        return render(request, "admin/ksiegowosc/invoice/import_jpk.html", context)

    def export_jpk_view(self, request):
        selected_ids_str = request.GET.get("ids")
        if not selected_ids_str:
            self.message_user(
                request,
                "Nie zaznaczono żadnych faktur do eksportu.",
                level=messages.WARNING,
            )
            return redirect("admin:ksiegowosc_invoice_changelist")
        selected_ids = selected_ids_str.split(",")
        queryset = self.get_queryset(request).filter(pk__in=selected_ids)
        if not queryset.exists():
            self.message_user(
                request, "Wybrane faktury nie zostały znalezione.", level=messages.ERROR
            )
            return redirect("admin:ksiegowosc_invoice_changelist")
        response = HttpResponse(content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="jpk_fa_wybrane_{datetime.now().strftime("%Y_%m_%d")}.xml"'
        )
        try:
            company_info = CompanyInfo.objects.get(user=request.user)
        except CompanyInfo.DoesNotExist:
            self.message_user(
                request,
                "Brak danych firmy. Uzupełnij je w pierwszej kolejności.",
                level=messages.ERROR,
            )
            return redirect("admin:ksiegowosc_invoice_changelist")
        ns = {
            "tns": "http://jpk.mf.gov.pl/wzor/2022/02/17/02171/",
            "etd": "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/",
        }
        ET.register_namespace("tns", ns["tns"])
        ET.register_namespace("etd", ns["etd"])
        root = ET.Element(f"{{{ns['tns']}}}JPK")
        daty = queryset.aggregate(
            min_date=Min("issue_date"), max_date=Max("issue_date")
        )
        data_od = daty["min_date"].strftime("%Y-%m-%d") if daty["min_date"] else ""
        data_do = daty["max_date"].strftime("%Y-%m-%d") if daty["max_date"] else ""
        header = ET.SubElement(root, f"{{{ns['tns']}}}Naglowek")
        ET.SubElement(
            header,
            f"{{{ns['tns']}}}KodFormularza",
            attrib={"kodSystemowy": "JPK_FA (4)", "wersjaSchemy": "1-0"},
        ).text = "JPK_FA"
        ET.SubElement(header, f"{{{ns['tns']}}}WariantFormularza").text = "4"
        ET.SubElement(
            header, f"{{{ns['tns']}}}DataWytworzeniaJPK"
        ).text = datetime.now().isoformat()
        if data_od and data_do:
            ET.SubElement(header, f"{{{ns['tns']}}}DataOd").text = data_od
            ET.SubElement(header, f"{{{ns['tns']}}}DataDo").text = data_do
        ET.SubElement(header, f"{{{ns['tns']}}}NazwaSystemu").text = "Fakturownia App"
        ET.SubElement(header, f"{{{ns['tns']}}}CelZlozenia").text = "1"
        ET.SubElement(header, f"{{{ns['tns']}}}KodUrzędu").text = (
            company_info.kod_urzedu or ""
        )
        podmiot = ET.SubElement(root, f"{{{ns['tns']}}}Podmiot1")
        identyfikator = ET.SubElement(podmiot, f"{{{ns['tns']}}}IdentyfikatorPodmiotu")
        ET.SubElement(
            identyfikator, f"{{{ns['tns']}}}NIP"
        ).text = company_info.tax_id.replace("-", "")
        ET.SubElement(
            identyfikator, f"{{{ns['tns']}}}PelnaNazwa"
        ).text = company_info.company_name
        adres_podmiotu = ET.SubElement(podmiot, f"{{{ns['tns']}}}AdresPodmiotu")
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}KodKraju").text = "PL"
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Wojewodztwo").text = (
            company_info.voivodeship or ""
        )
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Ulica").text = (
            company_info.street or ""
        )
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}Miejscowosc").text = (
            company_info.city or ""
        )
        ET.SubElement(adres_podmiotu, f"{{{ns['etd']}}}KodPocztowy").text = (
            company_info.zip_code or ""
        )
        for invoice in queryset:
            faktura = ET.SubElement(
                root, f"{{{ns['tns']}}}Faktura", attrib={"typ": "G"}
            )
            ET.SubElement(faktura, f"{{{ns['tns']}}}KodWaluty").text = "PLN"
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_1"
            ).text = invoice.issue_date.strftime("%Y-%m-%d")
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_2A").text = invoice.invoice_number
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_3A"
            ).text = invoice.contractor.name
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_3B"
            ).text = f"{invoice.contractor.street}, {invoice.contractor.zip_code} {invoice.contractor.city}"
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_3C"
            ).text = company_info.company_name
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_3D"
            ).text = company_info.get_full_address()
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_4B"
            ).text = company_info.tax_id.replace("-", "")
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_5B"
            ).text = invoice.contractor.tax_id.replace("-", "")
            ET.SubElement(
                faktura, f"{{{ns['tns']}}}P_6"
            ).text = invoice.sale_date.strftime("%Y-%m-%d")
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_13_7").text = str(
                invoice.total_amount
            )
            ET.SubElement(faktura, f"{{{ns['tns']}}}P_15").text = str(
                invoice.total_amount
            )
            if invoice.is_correction:
                ET.SubElement(faktura, f"{{{ns['tns']}}}RodzajFaktury").text = "KOREKTA"
                ET.SubElement(
                    faktura, f"{{{ns['tns']}}}PrzyczynaKorekty"
                ).text = invoice.correction_reason
                if invoice.corrected_invoice:
                    ET.SubElement(
                        faktura, f"{{{ns['tns']}}}NrFaKorygowanej"
                    ).text = invoice.corrected_invoice.invoice_number
            else:
                ET.SubElement(faktura, f"{{{ns['tns']}}}RodzajFaktury").text = "VAT"
            for item in invoice.items.all():
                wiersz = ET.SubElement(root, f"{{{ns['tns']}}}FakturaWiersz")
                ET.SubElement(
                    wiersz, f"{{{ns['tns']}}}P_2B"
                ).text = invoice.invoice_number
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_7").text = item.name
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_8A").text = str(item.quantity)
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_8B").text = item.unit
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_9A").text = str(
                    item.unit_price
                )
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_11").text = str(
                    item.total_price
                )
                ET.SubElement(wiersz, f"{{{ns['tns']}}}P_12").text = "zw"
        tree = ET.ElementTree(root)
        ET.indent(tree, space="\t", level=0)
        tree.write(response, encoding="utf-8", xml_declaration=True)
        return response

    def parse_jpk_file(self, xml_file, user):
        try:
            xml_content = xml_file.read()
            if isinstance(xml_content, bytes):
                try:
                    xml_content = xml_content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        xml_content = xml_content.decode("windows-1250")
                    except UnicodeDecodeError:
                        xml_content = xml_content.decode("iso-8859-2")
            if "JPK" not in xml_content and "Faktura" not in xml_content:
                raise ValueError("Plik nie zawiera danych JPK_FA")
            root = ET.fromstring(xml_content)
            namespaces = [
                {"tns": "http://jpk.mf.gov.pl/wzor/2022/02/17/02171/"},
                {"tns": "http://jpk.mf.gov.pl/wzor/2021/03/09/03091/"},
                {"tns": "http://jpk.mf.gov.pl/wzor/2020/03/09/03091/"},
                {"": ""},
            ]
            faktury_nodes = []
            ns = None
            for test_ns in namespaces:
                if "tns" in test_ns:
                    faktury_nodes = root.findall("tns:Faktura", test_ns)
                else:
                    faktury_nodes = root.findall(".//Faktura")
                if faktury_nodes:
                    ns = test_ns
                    break
            if not faktury_nodes:
                raise ValueError("Nie znaleziono elementów 'Faktura' w pliku JPK")
            all_invoice_items = self.collect_all_invoice_items(root, ns)
            return self.process_faktury_nodes(
                faktury_nodes, ns, user, all_invoice_items
            )
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}")

    def collect_all_invoice_items(self, root, ns):
        all_items = {}

        def get_text(node, paths):
            if not isinstance(paths, list):
                paths = [paths]
            for path in paths:
                if "tns" in ns and ns["tns"]:
                    found_node = node.find(f"tns:{path}", ns)
                else:
                    found_node = node.find(path)
                if found_node is not None and found_node.text:
                    return found_node.text.strip()
            return None

        if "tns" in ns and ns["tns"]:
            item_nodes = root.findall("tns:FakturaWiersz", ns)
        else:
            item_nodes = root.findall(".//FakturaWiersz")
        for item_node in item_nodes:
            invoice_number = get_text(item_node, ["P_2B", "2B"])
            if invoice_number:
                if invoice_number not in all_items:
                    all_items[invoice_number] = []
                item_data = {
                    "name": get_text(item_node, ["P_7", "7"]) or "Usługa",
                    "unit": get_text(item_node, ["P_8A", "8A"]) or "szt.",
                    "quantity": get_text(item_node, ["P_8B", "8B"]) or "1.00",
                    "unit_price": get_text(item_node, ["P_9B", "9B"]) or "0.00",
                    "total_price": get_text(item_node, ["P_11A", "11A"]) or "0.00",
                }
                all_items[invoice_number].append(item_data)
        return all_items

    def process_faktury_nodes(self, faktury_nodes, ns, user, all_invoice_items):
        def get_text(node, paths):
            if not isinstance(paths, list):
                paths = [paths]
            for path in paths:
                if "tns" in ns and ns["tns"]:
                    found_node = node.find(f"tns:{path}", ns)
                else:
                    found_node = node.find(path)
                if found_node is not None and found_node.text:
                    return found_node.text.strip()
            return None

        def parse_date(date_str):
            if not date_str:
                return datetime.now().date()
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    return datetime.strptime(date_str, "%d-%m-%Y").date()
                except ValueError:
                    return datetime.now().date()

        def parse_decimal(value_str):
            if not value_str:
                return Decimal("0.00")
            try:
                return Decimal(value_str.replace(",", ".").replace(" ", ""))
            except (InvalidOperation, ValueError):
                return Decimal("0.00")

        created_invoices = []
        import_warnings = []
        temp_invoice_counter = 0
        for faktura_node in faktury_nodes:
            try:
                invoice_number = get_text(faktura_node, ["P_2A", "2A", "NrFaktury"])
                buyer_nip = get_text(faktura_node, ["P_5B", "5B", "NIP"])
                buyer_name = get_text(faktura_node, ["P_3A", "3A", "Nazwa"])
                issue_date_str = get_text(faktura_node, ["P_1", "1", "DataWystawienia"])
                sale_date_str = get_text(faktura_node, ["P_6", "6", "DataSprzedazy"])
                total_amount_str = get_text(faktura_node, ["P_15", "WartoscBrutto"])
                notes_from_jpk = ""
                if not invoice_number:
                    temp_invoice_counter += 1
                    invoice_number = f"TEMP_JPK_{timezone.now().strftime('%Y%m%d%H%M%S')}_{temp_invoice_counter}"
                    notes_from_jpk = "Numer faktury został wygenerowany automatycznie podczas importu JPK."
                    import_warnings.append(
                        f"Faktura bez numeru: nadano tymczasowy numer '{invoice_number}'."
                    )
                if Invoice.objects.filter(
                    invoice_number=invoice_number, user=user
                ).exists():
                    import_warnings.append(
                        f"Pominięto: Faktura o numerze '{invoice_number}' już istnieje w systemie."
                    )
                    continue
                if buyer_nip:
                    contractor, created = Contractor.objects.get_or_create(
                        tax_id=buyer_nip,
                        user=user,
                        defaults={"name": buyer_name or "Brak nazwy w JPK"},
                    )
                else:
                    if not buyer_name:
                        import_warnings.append(
                            f"Pominięto fakturę (prawdopodobnie '{invoice_number}'): brak NIP i nazwy kontrahenta."
                        )
                        continue
                    contractor, created = Contractor.objects.get_or_create(
                        name=buyer_name, tax_id=None, user=user
                    )
                    if created:
                        import_warnings.append(
                            f"Utworzono nowego kontrahenta '{buyer_name}' bez numeru NIP."
                        )
                issue_date = parse_date(issue_date_str)
                sale_date = parse_date(sale_date_str) if sale_date_str else issue_date
                total_amount = parse_decimal(total_amount_str)
                is_correction = False
                correction_reason = None
                corrected_invoice = None
                original_items = []
                rodzaj_node = faktura_node.find(
                    "tns:RodzajFaktury" if "tns" in ns else "RodzajFaktury", ns
                )
                if (
                    rodzaj_node is not None
                    and "KOREKTA" in (rodzaj_node.text or "").upper()
                ):
                    is_correction = True
                    correction_reason = (
                        get_text(
                            faktura_node, ["PrzyczynaKorekty", "tns:PrzyczynaKorekty"]
                        )
                        or "Korekta faktury"
                    )
                    corrected_invoice_number = get_text(
                        faktura_node, ["NrFaKorygowanej", "tns:NrFaKorygowanej"]
                    )
                    if corrected_invoice_number:
                        try:
                            corrected_invoice = Invoice.objects.get(
                                invoice_number=corrected_invoice_number, user=user
                            )
                            original_items = list(
                                corrected_invoice.items.all().order_by("pk")
                            )
                        except Invoice.DoesNotExist:
                            correction_reason += f" (Faktura korygowana {corrected_invoice_number} nie istnieje w systemie)"
                            import_warnings.append(
                                f"Korekta '{invoice_number}': nie znaleziono w bazie faktury korygowanej {corrected_invoice_number}."
                            )
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
                    payment_method="przelew",
                    notes=notes_from_jpk,
                )
                correction_items_data = all_invoice_items.get(invoice_number, [])
                items_created = self.create_invoice_items_from_collected_data(
                    invoice,
                    user,
                    correction_items_data,
                    original_items if is_correction else [],
                )
                if items_created == 0 and total_amount > 0:
                    InvoiceItem.objects.create(
                        user=user,
                        invoice=invoice,
                        name="Usługi (import z JPK)",
                        quantity=Decimal("1.00"),
                        unit="szt.",
                        unit_price=total_amount,
                        total_price=total_amount,
                    )
                    items_created = 1
                if invoice.total_amount != total_amount:
                    invoice.total_amount = total_amount
                    invoice.save(update_fields=["total_amount"])
                created_invoices.append((invoice, items_created))
            except Exception as e:
                import_warnings.append(
                    f"Błąd krytyczny przy przetwarzaniu faktury: {str(e)}"
                )
                continue
        return created_invoices, import_warnings

    def create_invoice_items_from_collected_data(
        self, invoice, user, items_data, original_items=None
    ):
        if original_items is None:
            original_items = []
        items_created = 0

        def parse_decimal(value_str):
            if not value_str:
                return Decimal("0.00")
            try:
                return Decimal(value_str.replace(",", ".").replace(" ", ""))
            except (InvalidOperation, ValueError):
                return Decimal("0.00")

        for idx, item_data in enumerate(items_data):
            try:
                quantity = parse_decimal(item_data["quantity"])
                unit_price = parse_decimal(item_data["unit_price"])
                total_price = parse_decimal(item_data["total_price"])
                if total_price == 0 and quantity > 0 and unit_price > 0:
                    total_price = quantity * unit_price
                if unit_price == 0 and total_price > 0 and quantity > 0:
                    unit_price = total_price / quantity
                if quantity == 0:
                    quantity = Decimal("1.00")
                if total_price == 0:
                    total_price = unit_price
                new_item = InvoiceItem.objects.create(
                    user=user,
                    invoice=invoice,
                    name=item_data["name"] or "Usługa",
                    quantity=quantity,
                    unit=item_data["unit"] or "szt.",
                    unit_price=unit_price,
                    total_price=total_price,
                )
                if original_items and idx < len(original_items):
                    new_item.corrected_item = original_items[idx]
                    new_item.save()
                items_created += 1
            except Exception as e:
                continue
        return items_created

    def generate_pdf_view(self, request, object_id):
        queryset = self.get_queryset(request)
        try:
            invoice = queryset.get(pk=object_id)
        except Invoice.DoesNotExist:
            messages.error(
                request,
                "Faktura nie została znaleziona lub nie masz do niej uprawnień.",
            )
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        if not company_info:
            messages.error(
                request,
                "Nie można wygenerować PDF. Uzupełnij najpierw dane firmy w panelu.",
            )
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))
        html_string = render_to_string(
            "ksiegowosc/invoice_pdf_template.html",
            {"invoice": invoice, "company_info": company_info},
        )
        html = HTML(string=html_string)
        pdf = html.write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="faktura-{invoice.invoice_number.replace("/", "_")}.pdf"'
        )
        return response


# ==== MONTHLY SETTLEMENT ADMIN ====


@admin.register(MonthlySettlement)
class MonthlySettlementAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/monthlysettlement/change_list.html"
    list_display = (
        "year",
        "month",
        "total_revenue",
        "revenue_from_ewp",
        "health_insurance_paid",
        "income_tax_payable",
        "status",
        "user",
    )
    list_filter = ("status", "revenue_from_ewp", "year", "month", "user")
    search_fields = ("year", "month")
    readonly_fields = ("created_at", "approved_at", "details")
    exclude = ("user",)
    actions = ["approve_settlements"]

    @admin.action(description="Zatwierdź zaznaczone rozliczenia")
    def approve_settlements(self, request, queryset):
        updated = queryset.filter(status="draft").update(
            status="approved", approved_at=timezone.now()
        )
        messages.success(request, f"Zatwierdzono rozliczeń: {updated}.")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="ksiegowosc_dashboard",
            ),
            path(
                "oblicz/",
                self.admin_site.admin_view(self.calculate_view),
                name="ksiegowosc_monthlysettlement_calculate",
            ),
            path(
                "kalkulator-zus/",
                self.admin_site.admin_view(self.zus_calculator_view),
                name="ksiegowosc_monthlysettlement_zus_calculator",
            ),
            path(
                "import-jpk-ewp/",
                self.admin_site.admin_view(self.import_jpk_ewp_view),
                name="ksiegowosc_monthlysettlement_import_jpk_ewp",
            ),
        ]
        return my_urls + urls

    def import_jpk_ewp_view(self, request):
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            title="Import rozliczeń z JPK_EWP",
        )
        if request.method == "POST" and request.FILES.get("xml_file"):
            xml_file = request.FILES["xml_file"]
            try:
                if xml_file.size > 50 * 1024 * 1024:
                    messages.error(
                        request, "Plik jest za duży (maksymalny rozmiar to 50MB)."
                    )
                    return render(
                        request,
                        "admin/ksiegowosc/monthlysettlement/import_jpk_ewp.html",
                        context,
                    )
                if not xml_file.name.lower().endswith(".xml"):
                    messages.error(
                        request,
                        "Nieprawidłowe rozszerzenie pliku. Wymagany jest plik .xml.",
                    )
                    return render(
                        request,
                        "admin/ksiegowosc/monthlysettlement/import_jpk_ewp.html",
                        context,
                    )
                with transaction.atomic():
                    created_count, updated_count, warnings = self.parse_jpk_ewp_file(
                        xml_file, request.user
                    )
                if created_count or updated_count:
                    messages.success(
                        request,
                        f"Import zakończony pomyślnie. Utworzono: {created_count}, zaktualizowano: {updated_count} rozliczeń.",
                    )
                else:
                    messages.info(
                        request, "Nie znaleziono nowych danych do importu w pliku."
                    )
                for warning in warnings:
                    messages.add_message(request, messages.WARNING, warning)
                return redirect("admin:ksiegowosc_monthlysettlement_changelist")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(
                    request,
                    f"Wystąpił nieoczekiwany błąd podczas przetwarzania pliku: {str(e)}",
                )
        return render(
            request, "admin/ksiegowosc/monthlysettlement/import_jpk_ewp.html", context
        )

    def parse_jpk_ewp_file(self, xml_file, user):
        try:
            xml_content = xml_file.read()
            if isinstance(xml_content, bytes):
                try:
                    xml_content = xml_content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        xml_content = xml_content.decode("windows-1250")
                    except UnicodeDecodeError:
                        xml_content = xml_content.decode("iso-8859-2")
            if "JPK" not in xml_content:
                raise ValueError("Plik nie wygląda na plik JPK.")
            root = ET.fromstring(xml_content)
            # Namespace wykrywany dynamicznie z pliku, zamiast na sztywno —
            # MF zmieniało schemat JPK_EWP (wariant 3: .../2022/02/01/02011/,
            # wariant 4: .../2024/10/30/10301/ i możliwe kolejne w przyszłości).
            if root.tag.startswith("{"):
                ns_uri = root.tag[1:root.tag.index("}")]
            else:
                ns_uri = "http://jpk.mf.gov.pl/wzor/2022/02/01/02011/"
            namespaces = {"tns": ns_uri}
            ewp_wiersze = root.findall("tns:EWPWiersz", namespaces)
            if not ewp_wiersze:
                raise ValueError("Nie znaleziono żadnych wpisów w pliku JPK_EWP.")

            def _row_revenue(wiersz):
                """Kwota przychodu z wiersza — układ kolumn różni się między
                wariantami JPK_EWP. Wariant 4 (2024+): kwota w K_8, bez K_11.
                Wariant 3 (starszy): suma K_7 + K_11."""
                k8 = wiersz.find("tns:K_8", namespaces)
                k11 = wiersz.find("tns:K_11", namespaces)
                if k11 is None and k8 is not None:
                    # Wariant 4 — jedna kolumna z kwotą.
                    return Decimal(k8.text or "0")
                k7 = wiersz.find("tns:K_7", namespaces)
                k7_val = Decimal(k7.text) if k7 is not None and k7.text else Decimal("0")
                k11_val = Decimal(k11.text) if k11 is not None and k11.text else Decimal("0")
                return k7_val + k11_val

            monthly_revenues = {}
            for wiersz in ewp_wiersze:
                date_str = wiersz.find("tns:K_2", namespaces).text
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                year_month = (date.year, date.month)
                revenue = _row_revenue(wiersz)
                if year_month not in monthly_revenues:
                    monthly_revenues[year_month] = Decimal("0.00")
                monthly_revenues[year_month] += revenue
            created_count = 0
            updated_count = 0
            warnings = []
            for (year, month), total_revenue in monthly_revenues.items():
                existing = MonthlySettlement.objects.filter(
                    user=user, year=year, month=month
                ).first()
                if existing is None:
                    # Nowy miesiąc: sam przychód; wpłaty i zaliczkę uzupełni rozliczenie
                    MonthlySettlement.objects.create(
                        user=user,
                        year=year,
                        month=month,
                        total_revenue=total_revenue,
                        health_insurance_paid=0,
                        social_insurance_paid=0,
                        labor_fund_paid=0,
                        income_tax_payable=0,
                        status="imported",
                        revenue_from_ewp=True,
                    )
                    created_count += 1
                    continue
                # Istniejące rozliczenie: aktualizujemy tylko przychód, wpłat nie zerujemy
                if existing.status == "approved" and existing.total_revenue != total_revenue:
                    warnings.append(
                        f"{month:02d}/{year}: zmienił się przychód zatwierdzonego rozliczenia "
                        f"({existing.total_revenue} → {total_revenue} zł) — przelicz je."
                    )
                existing.total_revenue = total_revenue
                existing.revenue_from_ewp = True
                existing.save(update_fields=["total_revenue", "revenue_from_ewp"])
                updated_count += 1
            if created_count:
                warnings.append(
                    "Nowe miesiące mają status „Import JPK_EWP” — wpłaty składek i zaliczki "
                    "wyliczy asystent (zamknięcie miesiąca) albo formularz rozliczenia."
                )
            return created_count, updated_count, warnings
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}")

    def dashboard_view(self, request):
        context = {
            "opts": self.model._meta,
            "title": "Dashboard - Podsumowanie działalności",
            "current_year": datetime.now().year,
            "current_month": datetime.now().month,
        }
        current_year = datetime.now().year
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        today = timezone.now().date()
        current_yearly_settlement = YearlySettlement.objects.filter(
            user=request.user, year=current_year
        ).first()
        current_year_summary = {
            "total_revenue": Invoice.objects.filter(
                user=request.user, issue_date__year=current_year
            ).aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0"),
            "total_social_insurance": MonthlySettlement.objects.filter(
                user=request.user, year=current_year
            ).aggregate(total=Sum("social_insurance_paid"))["total"]
            or Decimal("0"),
            "total_health_insurance": MonthlySettlement.objects.filter(
                user=request.user, year=current_year
            ).aggregate(total=Sum("health_insurance_paid"))["total"]
            or Decimal("0"),
            "total_labor_fund": MonthlySettlement.objects.filter(
                user=request.user, year=current_year
            ).aggregate(total=Sum("labor_fund_paid"))["total"]
            or Decimal("0"),
            "total_monthly_tax": MonthlySettlement.objects.filter(
                user=request.user, year=current_year
            ).aggregate(total=Sum("income_tax_payable"))["total"]
            or Decimal("0"),
        }
        tax_base = (
            current_year_summary["total_revenue"]
            - current_year_summary["total_social_insurance"]
        )
        tax_base_after_health = tax_base - (
            current_year_summary["total_health_insurance"] / 2
        )
        if tax_base_after_health < 0:
            tax_base_after_health = Decimal("0")
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        tax_rate = Decimal("14.0")
        if company_info and company_info.lump_sum_rate:
            tax_rate = Decimal(company_info.lump_sum_rate)
        projected_yearly_tax = (tax_base_after_health * tax_rate / 100).quantize(
            Decimal("0.01")
        )
        projected_difference = (
            projected_yearly_tax - current_year_summary["total_monthly_tax"]
        )
        current_year_summary.update(
            {
                "tax_base": tax_base,
                "tax_base_after_health": tax_base_after_health,
                "projected_yearly_tax": projected_yearly_tax,
                "projected_difference": projected_difference,
                "tax_rate": tax_rate,
            }
        )
        context["current_year_summary"] = current_year_summary
        context["current_yearly_settlement"] = current_yearly_settlement
        context["company_info"] = company_info
        payment_stats = {
            "total_outstanding": Invoice.objects.filter(user=request.user).aggregate(
                total=Sum("total_amount")
            )["total"]
            or Decimal("0"),
            "total_paid": Payment.objects.filter(
                user=request.user, status="completed"
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0"),
            "overdue_count": Invoice.objects.filter(
                user=request.user, payment_date__lt=today
            )
            .annotate(paid_sum=Sum("payments__amount"))
            .exclude(paid_sum__gte=F("total_amount"))
            .count(),
        }
        payment_stats["balance_due"] = (
            payment_stats["total_outstanding"] - payment_stats["total_paid"]
        )
        previous_year = current_year - 1
        previous_year_data = {
            "total_revenue": Invoice.objects.filter(
                user=request.user, issue_date__year=previous_year
            ).aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0"),
            "total_tax_paid": MonthlySettlement.objects.filter(
                user=request.user, year=previous_year
            ).aggregate(total=Sum("income_tax_payable"))["total"]
            or Decimal("0"),
        }
        revenue_change = 0
        tax_change = 0
        if previous_year_data["total_revenue"] > 0:
            revenue_change = (
                (
                    current_year_summary["total_revenue"]
                    - previous_year_data["total_revenue"]
                )
                / previous_year_data["total_revenue"]
                * 100
            )
        if previous_year_data["total_tax_paid"] > 0:
            tax_change = (
                (
                    current_year_summary["total_monthly_tax"]
                    - previous_year_data["total_tax_paid"]
                )
                / previous_year_data["total_tax_paid"]
                * 100
            )
        context["previous_year_data"] = previous_year_data
        context["revenue_change"] = revenue_change
        context["tax_change"] = tax_change
        start_of_year = datetime(current_year, 1, 1)
        end_of_year = datetime(current_year, 12, 31)
        days_in_year = (end_of_year - start_of_year).days + 1
        days_passed = (datetime.now() - start_of_year).days + 1
        year_progress = (days_passed / days_in_year) * 100
        if days_passed > 0:
            daily_revenue = current_year_summary["total_revenue"] / days_passed
            projected_end_year_revenue = daily_revenue * days_in_year
            daily_tax = current_year_summary["total_monthly_tax"] / days_passed
            projected_end_year_tax = daily_tax * days_in_year
        else:
            projected_end_year_revenue = current_year_summary["total_revenue"]
            projected_end_year_tax = current_year_summary["total_monthly_tax"]
        context["year_progress"] = {
            "percentage": round(year_progress, 1),
            "days_passed": days_passed,
            "days_total": days_in_year,
            "projected_end_year_revenue": projected_end_year_revenue,
            "projected_end_year_tax": projected_end_year_tax,
        }
        monthly_tax_base, tax_base_labels = [], []
        for month in range(1, 13):
            monthly_revenue = Invoice.objects.filter(
                user=request.user,
                issue_date__year=current_year,
                issue_date__month=month,
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
            monthly_social = MonthlySettlement.objects.filter(
                user=request.user, year=current_year, month=month
            ).aggregate(total=Sum("social_insurance_paid"))["total"] or Decimal("0")
            base = monthly_revenue - monthly_social
            monthly_tax_base.append(float(base))
            tax_base_labels.append(f"{month:02d}/{current_year}")
        context["tax_base_chart"] = {
            "labels": json.dumps(tax_base_labels),
            "data": json.dumps(monthly_tax_base),
        }
        years_comparison, comparison_labels = [], []
        for year in range(current_year - 2, current_year + 1):
            yearly_revenue = Invoice.objects.filter(
                user=request.user, issue_date__year=year
            ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
            years_comparison.append(float(yearly_revenue))
            comparison_labels.append(str(year))
        context["years_comparison_chart"] = {
            "labels": json.dumps(comparison_labels),
            "data": json.dumps(years_comparison),
        }
        monthly_revenue_qs = (
            Invoice.objects.filter(user=request.user, issue_date__gte=start_date)
            .annotate(month=TruncMonth("issue_date"))
            .values("month")
            .annotate(total=Sum("total_amount"))
            .order_by("month")
        )
        revenue_labels, revenue_data = [], []
        for item in monthly_revenue_qs:
            revenue_labels.append(item["month"].strftime("%Y-%m"))
            revenue_data.append(float(item["total"] or 0))
        context["revenue_chart"] = {
            "labels": json.dumps(revenue_labels),
            "data": json.dumps(revenue_data),
        }
        monthly_payments = (
            Payment.objects.filter(
                user=request.user, payment_date__gte=start_date, status="completed"
            )
            .annotate(month=TruncMonth("payment_date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        payments_labels, payments_data = [], []
        for item in monthly_payments:
            payments_labels.append(item["month"].strftime("%Y-%m"))
            payments_data.append(float(item["total"] or 0))
        payment_status_stats = {
            "paid": Invoice.objects.filter(user=request.user)
            .annotate(paid_sum=Sum("payments__amount"))
            .filter(paid_sum__gte=F("total_amount"))
            .distinct()
            .count(),
            "partial": Invoice.objects.filter(user=request.user)
            .annotate(paid_sum=Sum("payments__amount"))
            .filter(paid_sum__gt=0, paid_sum__lt=F("total_amount"))
            .distinct()
            .count(),
            "overdue": Invoice.objects.filter(user=request.user, payment_date__lt=today)
            .annotate(paid_sum=Sum("payments__amount"))
            .exclude(paid_sum__gte=F("total_amount"))
            .count(),
            "unpaid": Invoice.objects.filter(user=request.user)
            .filter(payments__isnull=True)
            .count(),
        }
        context["recent_invoices"] = Invoice.objects.filter(user=request.user).order_by(
            "-issue_date"
        )[:5]
        pending_settlements = [
            m
            for m in range(1, 13)
            if not MonthlySettlement.objects.filter(
                user=request.user, year=current_year, month=m
            ).exists()
            and m <= datetime.now().month
        ]
        context["pending_settlements"] = pending_settlements
        reminders = []
        if datetime.now().month == 12:
            reminders.append(
                {
                    "type": "warning",
                    "icon": "fas fa-calendar-alt",
                    "title": "Zbliża się koniec roku podatkowego",
                    "message": "Pamiętaj o przygotowaniu rozliczenia rocznego do 31 stycznia.",
                    "action_url": "admin:ksiegowosc_yearlysettlement_calculate",
                    "action_text": "Sprawdź rozliczenie",
                }
            )
        if (
            datetime.now().month <= 3
            and not YearlySettlement.objects.filter(
                user=request.user, year=previous_year
            ).exists()
        ):
            reminders.append(
                {
                    "type": "danger",
                    "icon": "fas fa-exclamation-triangle",
                    "title": f"Brak rozliczenia rocznego za {previous_year}",
                    "message": f"Termin składania rozliczenia rocznego za {previous_year} mija 31 stycznia {current_year}.",
                    "action_url": "admin:ksiegowosc_yearlysettlement_calculate",
                    "action_text": "Oblicz teraz",
                }
            )
        if abs(projected_difference) > 1000:
            if projected_difference > 0:
                reminders.append(
                    {
                        "type": "warning",
                        "icon": "fas fa-money-bill-wave",
                        "title": "Prognozowana dopłata podatku",
                        "message": f"Na koniec roku możesz mieć dopłatę około {projected_difference:.0f} PLN.",
                        "action_url": "admin:ksiegowosc_monthlysettlement_calculate",
                        "action_text": "Sprawdź rozliczenia",
                    }
                )
            else:
                reminders.append(
                    {
                        "type": "success",
                        "icon": "fas fa-coins",
                        "title": "Prognozowany zwrot podatku",
                        "message": f"Na koniec roku możesz mieć zwrot około {abs(projected_difference):.0f} PLN.",
                        "action_url": "admin:ksiegowosc_yearlysettlement_calculate",
                        "action_text": "Zobacz szczegóły",
                    }
                )
        (
            context["payment_stats"],
            context["payments_chart"],
            context["payment_status_stats"],
            context["reminders"],
        ) = (
            payment_stats,
            {"labels": json.dumps(payments_labels), "data": json.dumps(payments_data)},
            payment_status_stats,
            reminders,
        )
        return render(request, "admin/enhanced_dashboard.html", context)

    def calculate_view(self, request):
        """Rozliczenie miesięczne liczone silnikiem (ksiegowosc.tax_engine) — stawka z danych firmy."""
        from . import settlements
        from .tax_engine import MissingYearParams

        context = {
            "opts": self.model._meta,
            "title": "Obliczanie Rozliczenia Miesięcznego",
        }
        today = timezone.localdate()
        context["years"], context["months"] = (
            list(range(today.year - 5, today.year + 1)),
            list(range(1, 13)),
        )
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        context["company_info"] = company_info
        if company_info:
            # Podpowiedź kwot: składki należne za bieżący miesiąc wg silnika
            try:
                due = settlements.monthly_obligations(request.user, today.year, today.month)
                zus = due["zus_za_miesiac"]
                context["calculated_rates"] = {
                    "base": zus["spoleczne"]["podstawa"],
                    "social_insurance_total": zus["spoleczne"]["spoleczne_razem"],
                    "labor_fund": zus["spoleczne"]["fundusz_pracy"],
                    "health_insurance_total": zus["zdrowotna"]["skladka"],
                }
                context["zus_rates"] = {"year": today.year}
            except (settlements.SettlementError, MissingYearParams) as exc:
                messages.warning(request, str(exc))
        if request.method == "POST":
            try:
                year = int(request.POST.get("year"))
                month = int(request.POST.get("month"))

                def amount(name):
                    return Decimal((request.POST.get(name) or "0").replace(",", ".").replace(" ", ""))

                settlement, created, _ = settlements.save_monthly_settlement(
                    request.user,
                    year,
                    month,
                    health_paid=amount("health_insurance_paid"),
                    social_paid=amount("social_insurance_paid"),
                    labor_fund_paid=amount("labor_fund_paid"),
                    status="approved",
                    overwrite_approved=True,
                )
                context["settlement"], context["submitted"] = settlement, True
            except (settlements.SettlementError, MissingYearParams, InvalidOperation, ValueError) as exc:
                messages.error(request, f"Błąd podczas obliczania: {exc}")
        return render(request, "ksiegowosc/settlement_form.html", context)

    def zus_calculator_view(self, request):
        """Kalkulator składek liczony silnikiem (ksiegowosc.tax_engine)."""
        from . import settlements
        from .tax_engine import (
            YEAR_PARAMS,
            ZUS_VARIANT_LABELS,
            MissingYearParams,
            get_year_params,
            lump_sum_health_contribution,
            social_contributions,
        )

        today = timezone.localdate()
        try:
            year = int(request.GET.get("year", today.year))
        except ValueError:
            year = today.year
        context = {
            "opts": self.model._meta,
            "title": "Kalkulator składek ZUS",
            "year": year,
            "available_years": sorted(YEAR_PARAMS),
        }
        try:
            params = get_year_params(year)
        except MissingYearParams as exc:
            context["error"] = str(exc)
            return render(request, "ksiegowosc/zus_calculator.html", context)
        context["params"] = params

        revenue_ytd = None
        company = CompanyInfo.objects.filter(user=request.user).first()
        if company:
            profile = company.contribution_profile()
            context["variant_label"] = ZUS_VARIANT_LABELS[profile.zus_variant]
            try:
                social = social_contributions(year, profile)
                context["social"] = social.as_dict()
            except ValueError as exc:
                context["error"] = str(exc)
                social = None
            end = today if year == today.year else date(year, 12, 31)
            revenue_ytd = settlements.revenue_between(
                request.user, date(year, 1, 1), end, Decimal(company.lump_sum_rate or "14")
            ).total
            if social is not None and profile.tax_form == "ryczalt_ewidencjonowany":
                health = lump_sum_health_contribution(year, revenue_ytd)["skladka"]
                context["monthly_total"] = social.total + health
        context["revenue_ytd"] = revenue_ytd

        tiers = []
        lower = Decimal("0")
        for threshold, _ in params.lump_sum_health_thresholds:
            probe = threshold if threshold is not None else lower + 1
            amount = lump_sum_health_contribution(year, probe)["skladka"]
            label = (
                f"przychód do {threshold:,.0f} zł".replace(",", " ")
                if threshold is not None
                else f"przychód powyżej {lower:,.0f} zł".replace(",", " ")
            )
            if revenue_ytd is None:
                active = False
            elif threshold is None:
                active = revenue_ytd > lower
            else:
                active = revenue_ytd <= threshold and (revenue_ytd > lower or lower == 0)
            tiers.append({"label": label, "amount": amount, "active": active})
            if threshold is not None:
                lower = threshold
        context["health_tiers"] = tiers
        return render(request, "ksiegowosc/zus_calculator.html", context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== YEARLY SETTLEMENT ADMIN ====


@admin.register(YearlySettlement)
class YearlySettlementAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/yearlysettlement/change_list.html"
    list_display = (
        "year",
        "total_yearly_revenue",
        "calculated_yearly_tax",
        "tax_difference",
        "get_settlement_type_display",
        "user",
    )
    list_filter = ("year", "user")
    readonly_fields = (
        "tax_difference",
        "calculated_yearly_tax",
        "total_yearly_revenue",
        "created_at",
    )
    exclude = ("user",)
    fieldsets = (
        ("Podstawowe informacje", {"fields": ("year", "tax_rate_used")}),
        (
            "Podsumowanie przychodów",
            {"fields": ("total_yearly_revenue",), "classes": ("collapse",)},
        ),
        (
            "Składki ZUS",
            {
                "fields": (
                    "total_social_insurance_paid",
                    "total_health_insurance_paid",
                    "total_labor_fund_paid",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Obliczenia podatkowe",
            {
                "fields": (
                    "total_monthly_tax_paid",
                    "calculated_yearly_tax",
                    "tax_difference",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Dodatkowe", {"fields": ("notes", "created_at"), "classes": ("collapse",)}),
    )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "oblicz-roczne/",
                self.admin_site.admin_view(self.calculate_yearly_view),
                name="ksiegowosc_yearlysettlement_calculate",
            ),
            path(
                "<int:object_id>/pdf/",
                self.admin_site.admin_view(self.generate_yearly_pdf_view),
                name="ksiegowosc_yearlysettlement_pdf",
            ),
            path(
                "<int:object_id>/podglad/",
                self.admin_site.admin_view(self.view_yearly_settlement),
                name="ksiegowosc_yearlysettlement_view",
            ),
        ]
        return my_urls + urls

    def calculate_yearly_view(self, request):
        """Rozliczenie roczne (PIT-28) liczone silnikiem z przychodów wg stawek i zapłaconych składek."""
        from . import settlements
        from .tax_engine import MissingYearParams

        context = {"opts": self.model._meta, "title": "Obliczanie Rozliczenia Rocznego"}
        if request.method == "POST":
            try:
                year = int(request.POST.get("year"))
                notes = request.POST.get("notes", "")
                settlement, created, result = settlements.save_annual_settlement(request.user, year, notes=notes)
                for note in result["uwagi"]:
                    messages.info(request, note)
                health = result["zdrowotna_roczna"]
                diff_key = "doplata" if "doplata" in health else "nadplata"
                messages.info(
                    request,
                    f"Roczna składka zdrowotna: {diff_key} {health[diff_key]} zł "
                    f"(termin {health['termin']:%d.%m.%Y}).",
                )
                context.update(
                    {
                        "yearly_settlement": settlement,
                        "monthly_settlements": MonthlySettlement.objects.filter(
                            user=request.user, year=year
                        ).order_by("month"),
                        "submitted": True,
                        "created": created,
                    }
                )
            except (settlements.SettlementError, MissingYearParams, ValueError) as exc:
                messages.error(request, f"Błąd podczas obliczania: {exc}")
        company = CompanyInfo.objects.filter(user=request.user).first()
        context.update(
            {
                "years": range(datetime.now().year - 5, datetime.now().year + 1),
                "default_tax_rate": company.lump_sum_rate if company and company.lump_sum_rate else "14.00",
            }
        )
        return render(request, "ksiegowosc/yearly_settlement_form.html", context)

    def generate_yearly_pdf_view(self, request, object_id):
        queryset = self.get_queryset(request)
        try:
            settlement = queryset.get(pk=object_id)
        except YearlySettlement.DoesNotExist:
            messages.error(request, "Rozliczenie roczne nie zostało znalezione.")
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        if not company_info:
            messages.error(
                request, "Nie można wygenerować PDF. Uzupełnij najpierw dane firmy."
            )
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))
        monthly = MonthlySettlement.objects.filter(
            user=request.user, year=settlement.year
        ).order_by("month")
        html = HTML(
            string=render_to_string(
                "ksiegowosc/yearly_settlement_pdf_template.html",
                {
                    "yearly_settlement": settlement,
                    "company_info": company_info,
                    "monthly_settlements": monthly,
                },
            )
        )
        response = HttpResponse(html.write_pdf(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="rozliczenie-roczne-{settlement.year}_{company_info.company_name.replace(" ", "_")}.pdf"'
        )
        return response

    def view_yearly_settlement(self, request, object_id):
        queryset = self.get_queryset(request)
        try:
            settlement = queryset.get(pk=object_id)
        except YearlySettlement.DoesNotExist:
            messages.error(request, "Rozliczenie roczne nie zostało znalezione.")
            return redirect("admin:ksiegowosc_yearlysettlement_changelist")
        context = {
            "opts": self.model._meta,
            "title": f"Podgląd rozliczenia rocznego {settlement.year}",
            "yearly_settlement": settlement,
            "monthly_settlements": MonthlySettlement.objects.filter(
                user=request.user, year=settlement.year
            ).order_by("month"),
            "submitted": True,
            "view_mode": True,
        }
        return render(request, "ksiegowosc/yearly_settlement_view.html", context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== ZUS RATES ADMIN ====


@admin.register(ZUSRates)
class ZUSRatesAdmin(admin.ModelAdmin):
    list_display = ("year", "minimum_wage", "minimum_base", "is_current", "updated_at")
    list_filter = ("year", "is_current")
    readonly_fields = ("updated_at",)
    fieldsets = (
        (
            "Podstawowe informacje",
            {"fields": ("year", "is_current", "source_url", "updated_at")},
        ),
        ("Podstawy wymiaru", {"fields": ("minimum_wage", "minimum_base")}),
        (
            "Stawki składek społecznych",
            {"fields": ("pension_rate", "disability_rate", "accident_rate")},
        ),
        (
            "Inne składki",
            {
                "fields": (
                    "labor_fund_rate",
                    "health_insurance_rate",
                    "health_insurance_deductible_rate",
                )
            },
        ),
        (
            "Preferencje i ulgi",
            {
                "fields": (
                    "preferential_pension_rate",
                    "preferential_months",
                    "small_zus_plus_threshold",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "aktualizuj-stawki/",
                self.admin_site.admin_view(self.update_rates_view),
                name="ksiegowosc_zusrates_update",
            )
        ]
        return my_urls + urls

    def update_rates_view(self, request):
        from io import StringIO

        from django.core.management import call_command

        if request.method == "POST":
            try:
                out = StringIO()
                call_command("update_zus_rates", "--force", stdout=out)
                messages.success(
                    request, f"Stawki ZUS zostały zaktualizowane!\n{out.getvalue()}"
                )
            except Exception as e:
                messages.error(request, f"Błąd aktualizacji: {str(e)}")
        return redirect("admin:ksiegowosc_zusrates_changelist")


# ==== PURCHASE INVOICE ADMIN ====


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/purchaseinvoice/change_list.html"
    list_display = (
        "invoice_number",
        "supplier",
        "issue_date",
        "total_amount",
        "category",
        "payment_status_colored",
        "user",
    )

    list_filter = ("category", "is_paid", "issue_date", "supplier", "user")
    search_fields = ("invoice_number", "supplier__name", "description")
    readonly_fields = ("created_at", "updated_at")
    exclude = ("user",)
    autocomplete_fields = ["supplier"]

    def payment_status_colored(self, obj):
        status, colors = (
            obj.payment_status,
            {"paid": "green", "overdue": "red", "pending": "orange"},
        )
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(status, "black"),
            obj.payment_status_display,
        )

    payment_status_colored.short_description = "Status płatności"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "import-ksef/",
                self.admin_site.admin_view(self.import_ksef_view),
                name="ksiegowosc_purchaseinvoice_import_ksef",
            ),
        ]
        return my_urls + urls

    def import_ksef_view(self, request):
        from ksef.ksef2_import import import_purchase_invoices_from_ksef

        try:
            company_info = CompanyInfo.objects.get(user=request.user)
        except CompanyInfo.DoesNotExist:
            messages.error(request, "Uzupełnij najpierw dane firmy (CompanyInfo) i token KSeF.")
            return redirect("admin:ksiegowosc_purchaseinvoice_changelist")

        if request.method == "POST":
            try:
                days = int(request.POST.get("days", 30))
            except (TypeError, ValueError):
                days = 30

            result = import_purchase_invoices_from_ksef(company_info, days=days)

            if result.created:
                messages.success(request, f"Zaimportowano {result.created} nowych faktur zakupowych z KSeF.")
            if result.skipped_existing:
                messages.info(request, f"Pominięto {result.skipped_existing} faktur już istniejących w bazie.")
            if result.errors:
                for err in result.errors[:10]:
                    messages.warning(request, err)
                if len(result.errors) > 10:
                    messages.warning(request, f"...i {len(result.errors) - 10} więcej błędów.")
            if not result.created and not result.errors:
                messages.info(request, "Brak nowych faktur do zaimportowania w podanym okresie.")

            return redirect("admin:ksiegowosc_purchaseinvoice_changelist")

        return render(
            request,
            "admin/ksiegowosc/purchaseinvoice/import_ksef.html",
            {"opts": self.model._meta, "title": "Import faktur zakupowych z KSeF", "company_info": company_info},
        )


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "user")
    list_filter = ("is_active", "user")
    search_fields = ("name", "code")
    exclude = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

# ==== DYŻURY MEDYCZNE (ordynacja dzienna) ====


@admin.register(DutyRate)
class DutyRateAdmin(admin.ModelAdmin):
    list_display = (
        "contractor",
        "valid_from",
        "rate_weekday_towarzyszacy",
        "rate_weekday_samodzielny",
        "rate_weekend_towarzyszacy",
        "rate_weekend_samodzielny",
        "user",
    )
    list_filter = ("contractor", "user")
    exclude = ("user",)
    ordering = ("-valid_from",)

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
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)


class BilledFilter(admin.SimpleListFilter):
    title = "rozliczenie"
    parameter_name = "billed"

    def lookups(self, request, model_admin):
        return (("no", "Nierozliczone"), ("yes", "Rozliczone (na fakturze)"))

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(invoice__isnull=True)
        if self.value() == "yes":
            return queryset.filter(invoice__isnull=False)
        return queryset


@admin.register(DutyShift)
class DutyShiftAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/dutyshift/change_list.html"
    list_display = (
        "date",
        "day_name",
        "contractor",
        "shift_type",
        "weekend_or_holiday_badge",
        "hours",
        "department",
        "value_preview",
        "invoice",
    )
    list_filter = ("contractor", "shift_type", "is_holiday", BilledFilter, "user")
    search_fields = ("department", "notes")
    date_hierarchy = "date"
    exclude = ("user", "invoice", "rate_applied")
    actions = ["generate_invoice_action", "download_annex_pdf_action"]

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}

    def day_name(self, obj):
        return DNI_TYGODNIA_PL[obj.date.weekday()]

    day_name.short_description = "Dzień tygodnia"

    def weekend_or_holiday_badge(self, obj):
        if obj.is_weekend_or_holiday:
            return mark_safe('<span style="color: #b30000; font-weight: bold;">weekend/święto</span>')
        return mark_safe('<span style="color: #555;">dzień roboczy</span>')

    weekend_or_holiday_badge.short_description = "Typ dnia"

    def value_preview(self, obj):
        val = obj.value
        if val is None:
            return mark_safe('<span style="color: orange;">brak stawki</span>')
        return f"{val} PLN"

    value_preview.short_description = "Wartość"

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
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "import-grafiku/",
                self.admin_site.admin_view(self.import_wklej_view),
                name="ksiegowosc_dutyshift_import",
            ),
            path(
                "zalacznik-pdf/",
                self.admin_site.admin_view(self.zalacznik_pdf_view),
                name="ksiegowosc_dutyshift_annex_pdf",
            ),
        ]
        return my_urls + urls

    def import_wklej_view(self, request):
        """Wklejenie grafiku dyżurów jako tekstu (np. skopiowanego z tabeli w rozmowie
        z Claude) i utworzenie z niego wielu DutyShift naraz.

        Oczekiwany format — jedna linia na dyżur, wartości oddzielone tabulatorem
        lub średnikiem:
            DATA;OD;DO;RODZAJ;OPK;UWAGI
            04.07.2026;20:00;8:00;samodzielny;;
            07.07.2026;18:00;8:00;towarzyszacy;500-00-16;

        RODZAJ: "samodzielny" / "sam" / "s" -> samodzielny, wszystko inne -> towarzyszący.
        Puste OPK i UWAGI można pominąć.
        """
        contractors = Contractor.objects.filter(user=request.user) if not request.user.is_superuser else Contractor.objects.all()

        if request.method == "POST":
            contractor_id = request.POST.get("contractor")
            raw_text = request.POST.get("raw_text", "")
            mark_holiday_dates = {
                d.strip() for d in request.POST.get("holiday_dates", "").split(",") if d.strip()
            }
            try:
                contractor = contractors.get(pk=contractor_id)
            except (Contractor.DoesNotExist, ValueError, TypeError):
                messages.error(request, "Wybierz prawidłowego kontrahenta.")
                return redirect("admin:ksiegowosc_dutyshift_import")

            created, errors = 0, []
            for line_no, line in enumerate(raw_text.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in re.split(r"[;\t]", line)]
                if len(parts) < 3:
                    errors.append(f"Linia {line_no}: za mało kolumn ('{line}')")
                    continue
                date_str, start_str, end_str = parts[0], parts[1], parts[2]
                rodzaj_str = parts[3].lower() if len(parts) > 3 and parts[3] else "towarzyszacy"
                opk = parts[4] if len(parts) > 4 else ""
                uwagi = parts[5] if len(parts) > 5 else ""

                shift_type = (
                    "samodzielny"
                    if rodzaj_str.startswith("sam") or rodzaj_str in ("s",)
                    else "towarzyszacy"
                )

                parsed_date = None
                for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
                    try:
                        parsed_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                if parsed_date is None:
                    errors.append(f"Linia {line_no}: nierozpoznana data '{date_str}'")
                    continue

                parsed_start = parsed_end = None
                for fmt in ("%H:%M", "%H"):
                    try:
                        parsed_start = datetime.strptime(start_str, fmt).time()
                        break
                    except ValueError:
                        continue
                for fmt in ("%H:%M", "%H"):
                    try:
                        parsed_end = datetime.strptime(end_str, fmt).time()
                        break
                    except ValueError:
                        continue
                if parsed_start is None or parsed_end is None:
                    errors.append(f"Linia {line_no}: nierozpoznane godziny '{start_str}'-'{end_str}'")
                    continue

                DutyShift.objects.create(
                    user=request.user,
                    contractor=contractor,
                    date=parsed_date,
                    start_time=parsed_start,
                    end_time=parsed_end,
                    shift_type=shift_type,
                    is_holiday=date_str in mark_holiday_dates or parsed_date.isoformat() in mark_holiday_dates,
                    department=opk,
                    notes=uwagi,
                )
                created += 1

            if created:
                messages.success(request, f"Zaimportowano {created} dyżurów.")
            for err in errors:
                messages.warning(request, err)
            return redirect("admin:ksiegowosc_dutyshift_changelist")

        return render(
            request,
            "admin/ksiegowosc/dutyshift/import.html",
            {"contractors": contractors, "opts": self.model._meta, "title": "Import grafiku dyżurów"},
        )

    @admin.action(description="Wystaw fakturę z zaznaczonych dyżurów")
    def generate_invoice_action(self, request, queryset):
        queryset = queryset.filter(invoice__isnull=True)
        if not queryset.exists():
            messages.warning(request, "Zaznaczone dyżury są już rozliczone lub nic nie zaznaczono.")
            return

        contractor_ids = set(queryset.values_list("contractor_id", flat=True))
        if len(contractor_ids) > 1:
            messages.error(request, "Zaznaczone dyżury dotyczą więcej niż jednego kontrahenta — wystaw je osobno.")
            return
        contractor = Contractor.objects.get(pk=contractor_ids.pop())

        missing_rate = []
        groups = {}  # (shift_type, is_weekend_or_holiday) -> {"hours": Decimal, "rate": Decimal}
        for shift in queryset:
            rate_obj = DutyRate.rate_object_for_date(request.user, contractor, shift.date)
            if not rate_obj:
                missing_rate.append(shift)
                continue
            rate = rate_obj.rate_for(
                is_weekend_or_holiday=shift.is_weekend_or_holiday, shift_type=shift.shift_type
            )
            key = (shift.shift_type, shift.is_weekend_or_holiday)
            group = groups.setdefault(key, {"hours": Decimal("0"), "rate": rate, "shifts": []})
            group["hours"] += shift.hours
            group["shifts"].append(shift)

        if missing_rate:
            dates = ", ".join(s.date.isoformat() for s in missing_rate)
            messages.error(
                request,
                f"Brak zdefiniowanej stawki (DutyRate) dla kontrahenta {contractor} na dzień(-i): {dates}. "
                "Dodaj stawkę i spróbuj ponownie.",
            )
            return

        last_invoice = Invoice.objects.filter(user=request.user).order_by("-id").first()
        next_number = f"DYZ/{timezone.now():%Y/%m}/{(last_invoice.id if last_invoice else 0) + 1}"

        with transaction.atomic():
            invoice = Invoice.objects.create(
                user=request.user,
                invoice_number=next_number,
                contractor=contractor,
            )
            labels = {
                ("samodzielny", False): "Dyżur medyczny samodzielny — dni robocze",
                ("samodzielny", True): "Dyżur medyczny samodzielny — weekend/święto",
                ("towarzyszacy", False): "Dyżur medyczny towarzyszący — dni robocze",
                ("towarzyszacy", True): "Dyżur medyczny towarzyszący — weekend/święto",
            }
            for key, group in groups.items():
                InvoiceItem.objects.create(
                    user=request.user,
                    invoice=invoice,
                    name=labels[key],
                    quantity=group["hours"],
                    unit="godz.",
                    unit_price=group["rate"],
                    total_price=group["hours"] * group["rate"],
                )
                for shift in group["shifts"]:
                    shift.invoice = invoice
                    shift.rate_applied = group["rate"]
                    shift.save(update_fields=["invoice", "rate_applied"])
            invoice.update_total_amount()

        messages.success(
            request,
            f"Wystawiono fakturę {invoice.invoice_number} na {invoice.total_amount} PLN "
            f"({queryset.count()} dyżurów). Uzupełnij numer faktury i wystaw załącznik PDF.",
        )

    @admin.action(description="Pobierz załącznik PDF dla zaznaczonych dyżurów")
    def download_annex_pdf_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        url = reverse("admin:ksiegowosc_dutyshift_annex_pdf") + f"?ids={ids}"
        return redirect(url)

    def zalacznik_pdf_view(self, request):
        MIESIACE_PL = [
            "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
            "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
        ]
        invoice_id = request.GET.get("invoice_id")
        ids_str = request.GET.get("ids")
        if invoice_id:
            shifts = DutyShift.objects.filter(invoice_id=invoice_id, user=request.user).order_by("date")
            invoice = Invoice.objects.filter(pk=invoice_id, user=request.user).first()
        elif ids_str:
            ids = ids_str.split(",")
            shifts = DutyShift.objects.filter(pk__in=ids, user=request.user).order_by("date")
            invoice = None
        else:
            messages.error(request, "Nie wskazano dyżurów do wygenerowania załącznika.")
            return redirect("admin:ksiegowosc_dutyshift_changelist")

        if not shifts.exists():
            messages.error(request, "Nie znaleziono dyżurów.")
            return redirect("admin:ksiegowosc_dutyshift_changelist")

        rows = [
            {
                "lp": i,
                "date": s.date,
                "day_name": DNI_TYGODNIA_PL[s.date.weekday()],
                "start_time": s.start_time,
                "end_time": s.end_time,
                "hours": s.hours,
                "department": s.department,
                "shift_type": s.get_shift_type_display(),
            }
            for i, s in enumerate(shifts, start=1)
        ]
        total_hours = sum((s.hours for s in shifts), Decimal("0"))

        html_string = render_to_string(
            "ksiegowosc/dutyshift_annex_pdf_template.html",
            {
                "rows": rows,
                "invoice": invoice,
                "total_hours": total_hours,
                "issue_month_pl": (
                    f"{MIESIACE_PL[invoice.issue_date.month - 1]} {invoice.issue_date.year}"
                    if invoice
                    else ""
                ),
            },
        )
        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        suffix = invoice.invoice_number.replace("/", "_") if invoice else timezone.now().strftime("%Y%m%d")
        response["Content-Disposition"] = f'attachment; filename="zalacznik-dyzury-{suffix}.pdf"'
        return response
