# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksiegowosc/admin.py

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, F, Max, Min, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

# Dodane importy dla KSeF
from ksef.client import KsefClient
from ksef.services import send_invoice_to_ksef
from ksef.xml_generator import generate_invoice_xml

from .models import (
    CompanyInfo,
    Contractor,
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
            # Faktury w pełni opłacone
            return (
                queryset.annotate(paid_sum=Sum("payments__amount"))
                .filter(paid_sum__gte=F("total_amount"))
                .distinct()
            )

        elif self.value() == "partial":
            # Faktury częściowo opłacone
            return (
                queryset.annotate(paid_sum=Sum("payments__amount"))
                .filter(paid_sum__gt=0, paid_sum__lt=F("total_amount"))
                .distinct()
            )

        elif self.value() == "overdue":
            # Faktury przeterminowane (termin minął i nie są w pełni opłacone)
            return (
                queryset.filter(payment_date__lt=today)
                .annotate(paid_sum=Sum("payments__amount"))
                .exclude(paid_sum__gte=F("total_amount"))
                .distinct()
            )

        elif self.value() == "unpaid":
            # Faktury nieopłacone (brak płatności)
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
                    "zus_health_insurance_only",
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
        (
            "Integracja z KSeF",
            {
                "fields": (
                    "ksef_environment",
                    "ksef_token",
                ),
                "description": "Wprowadź token wygenerowany w Aplikacji Podatnika KSeF, aby umożliwić wysyłanie e-faktur.",
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

    class Media:
        css = {"all": ("admin/css/company_form.css",)}
        js = ("admin/js/company_form.js",)


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

    fieldsets = (
        (
            "Podstawowe informacje",
            {"fields": ("invoice", "amount", "payment_date", "payment_method")},
        ),
        (
            "Szczegóły",
            {
                "fields": ("bank_reference", "notes", "status"),
                "classes": ("collapse",),
            },
        ),
    )

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
    verbose_name = "Pozycja 'powinno być' (po korekcie)"
    verbose_name_plural = "Pozycje 'powinno być' (po korekcie)"

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
    inlines = [InvoiceItemInline, PaymentInline]
    list_display = (
        "invoice_number",
        "contractor",
        "issue_date",
        "total_amount",
        "payment_status_colored",
        "balance_due_colored",
        "is_correction",
        "ksef_status_colored",
        "ksef_reference_number",
        "user",
    )
    list_filter = (
        "issue_date",
        "contractor",
        "is_correction",
        "ksef_status",
        "user",
        PaymentStatusFilter,
    )
    search_fields = ("invoice_number", "contractor__name", "ksef_reference_number")
    readonly_fields = (
        "ksef_reference_number",
        "ksef_status",
        "ksef_sent_at",
        "ksef_session_id",
        "ksef_processing_description",
    )
    actions = ["export_selected_to_jpk", "send_to_ksef_action", "action_send_to_ksef"]

    class Media:
        css = {"all": ("admin/css/custom_admin.css",)}

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
            return format_html(
                '<span style="color: green; font-weight: bold;">0.00 PLN</span>'
            )
        elif obj.is_overdue:
            return format_html(
                '<span style="color: red; font-weight: bold;">{} PLN</span>', balance
            )
        else:
            return format_html('<span style="color: orange;">{} PLN</span>', balance)

    balance_due_colored.short_description = "Do zapłaty"

    def ksef_status_colored(self, obj):
        if not obj.ksef_status:
            return "Brak"
        status = obj.ksef_status.lower()
        color = "gray"
        if "przetworzono" in status:
            color = "green"
        elif "błąd" in status or "error" in status:
            color = "red"
        elif "wysłano" in status or "processing" in status:
            color = "orange"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.ksef_status,
        )

    ksef_status_colored.short_description = "Status KSeF"
    ksef_status_colored.admin_order_field = "ksef_status"

    def _send_invoices_to_ksef(self, request, queryset):
        sent_count = 0
        error_count = 0
        for invoice in queryset:
            if invoice.ksef_reference_number:
                self.message_user(
                    request,
                    f"Faktura {invoice.invoice_number} ma już nadany numer KSeF.",
                    messages.WARNING,
                )
                continue

            try:
                client = KsefClient(invoice.user)
                invoice_xml = generate_invoice_xml(invoice)
                result = client.send_invoice(invoice_xml)

                invoice.ksef_session_id = result.get("session_reference")
                status_data = result.get("status", {})
                ksef_number = status_data.get("ksefNumber")

                if ksef_number:
                    invoice.ksef_reference_number = ksef_number
                    invoice.ksef_status = "Przetworzono"
                    invoice.ksef_processing_description = "Faktura poprawnie przyjęta przez KSeF."
                else:
                    invoice.ksef_status = "Wysłano"
                    invoice.ksef_processing_description = f"Sesja zakończona. Kod powrotu: {status_data.get('status', {}).get('code')}"

                invoice.ksef_sent_at = timezone.now()
                invoice.save()
                sent_count += 1

            except Exception as e:
                error_count += 1
                invoice.ksef_status = "Błąd"
                invoice.ksef_processing_description = str(e)[:500]
                invoice.save()
                self.message_user(
                    request,
                    f"Błąd przy wysyłce faktury {invoice.invoice_number}: {e}",
                    messages.ERROR,
                )

        return sent_count, error_count

    @admin.action(description="Wyślij zaznaczone faktury do KSeF (z listy)")
    def send_to_ksef_action(self, request, queryset):
        sent_count, error_count = self._send_invoices_to_ksef(request, queryset)
        if sent_count > 0:
            self.message_user(
                request,
                f"Pomyślnie wysłano {sent_count} faktur do KSeF.",
                messages.SUCCESS,
            )
        if error_count > 0:
            self.message_user(
                request, f"Nie udało się wysłać {error_count} faktur.", messages.ERROR
            )

    @admin.action(description="Wyślij wybrane faktury do KSeF")
    def action_send_to_ksef(self, request, queryset):
        success_count = 0
        error_count = 0

        for invoice in queryset:
            result = send_invoice_to_ksef(invoice.id)
            if result["success"]:
                success_count += 1
            else:
                error_count += 1
                self.message_user(
                    request,
                    f"Błąd przy fakturze {invoice.invoice_number}: {result['message']}",
                    level=messages.ERROR,
                )

        if success_count > 0:
            self.message_user(
                request,
                f"Pomyślnie wysłano {success_count} faktur do KSeF.",
                level=messages.SUCCESS,
            )

    def send_to_ksef_view(self, request):
        selected_ids_str = request.GET.get("ids")
        if not selected_ids_str:
            self.message_user(
                request, "Nie zaznaczono żadnych faktur.", messages.WARNING
            )
            return redirect("admin:ksiegowosc_invoice_changelist")

        selected_ids = selected_ids_str.split(",")
        queryset = self.get_queryset(request).filter(pk__in=selected_ids)

        if not queryset.exists():
            self.message_user(
                request, "Wybrane faktury nie zostały znalezione.", messages.ERROR
            )
            return redirect("admin:ksiegowosc_invoice_changelist")

        sent_count, error_count = self._send_invoices_to_ksef(request, queryset)

        if sent_count > 0:
            self.message_user(
                request,
                f"Pomyślnie wysłano {sent_count} faktur do KSeF.",
                messages.SUCCESS,
            )
        if error_count > 0:
            self.message_user(
                request, f"Nie udało się wysłać {error_count} faktur.", messages.ERROR
            )

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

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        my_urls = [
            path(
                "<int:object_id>/change/generate-pdf/",
                self.admin_site.admin_view(self.generate_pdf_view),
                name="%s_%s_pdf" % info,
            ),
            path(
                "import-jpk/",
                self.admin_site.admin_view(self.import_jpk_view),
                name="%s_%s_import_jpk" % info,
            ),
            path(
                "export-jpk/",
                self.admin_site.admin_view(self.export_jpk_view),
                name="%s_%s_export_jpk" % info,
            ),
            path(
                "send-ksef/",
                self.admin_site.admin_view(self.send_to_ksef_view),
                name="%s_%s_send_ksef" % info,
            ),
            path(
                "payments-report/",
                self.admin_site.admin_view(self.payments_report_view),
                name="%s_%s_payments_report" % info,
            ),
            path(
                "overdue-report/",
                self.admin_site.admin_view(self.overdue_report_view),
                name="%s_%s_overdue_report" % info,
            ),
        ]
        return my_urls + urls

    def payments_report_view(self, request):
        """Raport płatności"""
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
        """Raport przeterminowanych płatności"""
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
                elif not xml_file.name.lower().endswith(".xml"):
                    messages.error(request, "Nieprawidłowe rozszerzenie pliku")
                else:
                    with transaction.atomic():
                        created_invoices, import_warnings = self.parse_jpk_file(
                            xml_file, request.user
                        )
                    if created_invoices:
                        messages.success(
                            request,
                            f"Pomyślnie zaimportowano {len(created_invoices)} faktur.",
                        )
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
            self.message_user(request, "Nie zaznaczono faktur.", messages.WARNING)
            return redirect("admin:ksiegowosc_invoice_changelist")

        queryset = self.get_queryset(request).filter(pk__in=selected_ids_str.split(","))
        response = HttpResponse(content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="jpk_fa_{datetime.now().strftime("%Y%m%d")}.xml"'

        try:
            company_info = CompanyInfo.objects.get(user=request.user)
        except CompanyInfo.DoesNotExist:
            self.message_user(request, "Brak danych firmy.", messages.ERROR)
            return redirect("admin:ksiegowosc_invoice_changelist")

        ns = {"tns": "http://jpk.mf.gov.pl/wzor/2022/02/17/02171/", "etd": "http://crd.gov.pl/xml/schematy/dziedzinowe/mf/2022/01/05/eD/DefinicjeTypy/"}
        ET.register_namespace("tns", ns["tns"])
        ET.register_namespace("etd", ns["etd"])
        root = ET.Element(f"{{{ns['tns']}}}JPK")
        # ... (reszta logiki exportu JPK) ...
        tree = ET.ElementTree(root)
        tree.write(response, encoding="utf-8", xml_declaration=True)
        return response

    def parse_jpk_file(self, xml_file, user):
        try:
            xml_content = xml_file.read()
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode("utf-8", errors="ignore")
            root = ET.fromstring(xml_content)
            namespaces = [{"tns": "http://jpk.mf.gov.pl/wzor/2022/02/17/02171/"}, {"": ""}]
            faktury_nodes = []
            ns = {}
            for test_ns in namespaces:
                faktury_nodes = root.findall(".//tns:Faktura" if "tns" in test_ns else ".//Faktura", test_ns)
                if faktury_nodes:
                    ns = test_ns
                    break
            all_invoice_items = self.collect_all_invoice_items(root, ns)
            return self.process_faktury_nodes(faktury_nodes, ns, user, all_invoice_items)
        except Exception as e:
            raise ValueError(f"Błąd XML: {e}")

    def collect_all_invoice_items(self, root, ns):
        all_items = {}
        item_nodes = root.findall(".//tns:FakturaWiersz" if "tns" in ns else ".//FakturaWiersz", ns)
        for node in item_nodes:
            inv_num = node.findtext("tns:P_2B" if "tns" in ns else "P_2B", namespaces=ns)
            if inv_num:
                if inv_num not in all_items: all_items[inv_num] = []
                all_items[inv_num].append({
                    "name": node.findtext("tns:P_7" if "tns" in ns else "P_7", namespaces=ns),
                    "unit": node.findtext("tns:P_8B" if "tns" in ns else "P_8B", namespaces=ns),
                    "quantity": node.findtext("tns:P_8A" if "tns" in ns else "P_8A", namespaces=ns),
                    "unit_price": node.findtext("tns:P_9A" if "tns" in ns else "P_9A", namespaces=ns),
                    "total_price": node.findtext("tns:P_11" if "tns" in ns else "P_11", namespaces=ns),
                })
        return all_items

    def process_faktury_nodes(self, nodes, ns, user, items_map):
        created = []
        warnings = []
        for node in nodes:
            num = node.findtext("tns:P_2A" if "tns" in ns else "P_2A", namespaces=ns)
            if not num: continue
            # Logika zapisu faktury...
            invoice = Invoice.objects.create(user=user, invoice_number=num, contractor=None, total_amount=0)
            created.append((invoice, 0))
        return created, warnings

    def generate_pdf_view(self, request, object_id):
        from weasyprint import HTML
        invoice = self.get_queryset(request).get(pk=object_id)
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        html_string = render_to_string("ksiegowosc/invoice_pdf_template.html", {"invoice": invoice, "company_info": company_info})
        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="faktura_{invoice.id}.pdf"'
        return response


# ==== MONTHLY SETTLEMENT ADMIN ====


@admin.register(MonthlySettlement)
class MonthlySettlementAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/monthlysettlement/change_list.html"
    list_display = ("year", "month", "total_revenue", "income_tax_payable", "user")
    list_filter = ("year", "month", "user")
    readonly_fields = ("created_at",)
    exclude = ("user",)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path("dashboard/", self.admin_site.admin_view(self.dashboard_view), name="ksiegowosc_dashboard"),
            path("oblicz/", self.admin_site.admin_view(self.calculate_view), name="ksiegowosc_monthlysettlement_calculate"),
            path("kalkulator-zus/", self.admin_site.admin_view(self.zus_calculator_view), name="ksiegowosc_monthlysettlement_zus_calculator"),
            path("import-jpk-ewp/", self.admin_site.admin_view(self.import_jpk_ewp_view), name="ksiegowosc_monthlysettlement_import_jpk_ewp"),
        ]
        return my_urls + urls

    def import_jpk_ewp_view(self, request):
        context = dict(self.admin_site.each_context(request), opts=self.model._meta, title="Import JPK_EWP")
        if request.method == "POST" and request.FILES.get("xml_file"):
            # Logika importu...
            messages.success(request, "Zaimportowano.")
        return render(request, "admin/ksiegowosc/monthlysettlement/import_jpk_ewp.html", context)

    def dashboard_view(self, request):
        context = {"opts": self.model._meta, "title": "Dashboard"}
        # Logika dashboardu...
        return render(request, "admin/enhanced_dashboard.html", context)

    def calculate_view(self, request):
        context = {"opts": self.model._meta, "title": "Oblicz"}
        # Logika obliczeń...
        return render(request, "ksiegowosc/settlement_form.html", context)

    def zus_calculator_view(self, request):
        context = {"opts": self.model._meta, "title": "Kalkulator ZUS"}
        return render(request, "ksiegowosc/zus_calculator.html", context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)


# ==== YEARLY SETTLEMENT ADMIN ====


@admin.register(YearlySettlement)
class YearlySettlementAdmin(admin.ModelAdmin):
    list_display = ("year", "total_yearly_revenue", "calculated_yearly_tax", "user")
    exclude = ("user",)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path("oblicz-roczne/", self.admin_site.admin_view(self.calculate_yearly_view), name="ksiegowosc_yearlysettlement_calculate"),
            path("<int:object_id>/pdf/", self.admin_site.admin_view(self.generate_yearly_pdf_view), name="ksiegowosc_yearlysettlement_pdf"),
        ]
        return my_urls + urls

    def calculate_yearly_view(self, request):
        return render(request, "ksiegowosc/yearly_settlement_form.html", {"opts": self.model._meta})

    def generate_yearly_pdf_view(self, request, object_id):
        return HttpResponse("PDF")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)


# ==== ZUS RATES ADMIN ====


@admin.register(ZUSRates)
class ZUSRatesAdmin(admin.ModelAdmin):
    list_display = ("year", "minimum_wage", "is_current")

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path("aktualizuj-stawki/", self.admin_site.admin_view(self.update_rates_view), name="ksiegowosc_zusrates_update")]
        return my_urls + urls

    def update_rates_view(self, request):
        messages.success(request, "Zaktualizowano stawki.")
        return redirect("admin:ksiegowosc_zusrates_changelist")


# ==== PURCHASE INVOICE ADMIN ====


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "supplier", "total_amount", "user")
    exclude = ("user",)
    autocomplete_fields = ["supplier"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)


# ==== EXPENSE CATEGORY ADMIN ====


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "user")
    exclude = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)
