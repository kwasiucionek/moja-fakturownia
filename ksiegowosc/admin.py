# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksiegowosc/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from ksef.services import send_invoice_to_ksef

# Dodane importy dla KSeF
from ksef.client import KsefClient
from ksef.xml_generator import generate_invoice_xml

from .models import (
    CompanyInfo,
    Contractor,
    Invoice,
    InvoiceItem,
    MonthlySettlement,
    YearlySettlement,
    ZUSRates,
    Payment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    ExpenseCategory,
)
from django.contrib import messages
from django.db.models import Sum, Min, Max, Count, Q, F
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.utils.html import format_html
import json


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
    actions = ["export_selected_to_jpk", "send_to_ksef", "action_send_to_ksef"]

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
                # 1. Sprawdzenie czy już nie wysłano
                if invoice.ksef_reference_number:
                    self.message_user(
                        request,
                        f"Faktura {invoice.invoice_number} ma już nadany numer KSeF.",
                        messages.WARNING,
                    )
                    continue

                try:
                    # 2. Inicjalizacja klienta dla użytkownika faktury
                    # Upewnij się, że ten użytkownik ma uzupełnione CompanyInfo z tokenem!
                    client = KsefClient(invoice.user)

                    # 3. Generowanie XML
                    invoice_xml = generate_invoice_xml(invoice)

                    # 4. Wysyłka (to trwa kilka sekund - autoryzacja + wysyłka + status)
                    result = client.send_invoice(invoice_xml)

                    # 5. Aktualizacja danych w bazie na podstawie wyniku z client.py
                    invoice.ksef_session_id = result.get("session_reference")

                    # Pobranie statusu i numeru KSeF z odpowiedzi
                    status_data = result.get("status", {})
                    ksef_number = status_data.get("ksefNumber")

                    if ksef_number:
                        invoice.ksef_reference_number = ksef_number
                        invoice.ksef_status = "Przetworzono"
                        invoice.ksef_processing_description = "Faktura poprawnie przyjęta przez KSeF."
                    else:
                        # Jeśli nie ma numeru KSeF, ale nie było błędu, to może wciąż jest przetwarzana
                        invoice.ksef_status = "Wysłano"
                        invoice.ksef_processing_description = f"Sesja zakończona. Kod powrotu: {status_data.get('status', {}).get('code')}"

                    invoice.ksef_sent_at = timezone.now()
                    invoice.save()

                    sent_count += 1

                except Exception as e:
                    error_count += 1
                    # Zapisujemy informację o błędzie w fakturze, żeby użytkownik widział co się stało
                    invoice.ksef_status = "Błąd"
                    invoice.ksef_processing_description = str(e)[:500] # Przycinamy zbyt długie komunikaty
                    invoice.save()

                    # Logowanie błędu do messages w adminie
                    self.message_user(
                        request,
                        f"Błąd przy wysyłce faktury {invoice.invoice_number}: {e}",
                        messages.ERROR,
                    )

            return sent_count, error_count

    @admin.action(description="Wyślij zaznaczone faktury do KSeF (z listy)")
    def send_to_ksef(self, request, queryset):
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

    @admin.action(description='Wyślij wybrane faktury do KSeF')
        def action_send_to_ksef(self, request, queryset):
            success_count = 0
            error_count = 0

            for invoice in queryset:
                # Wywołanie logiki z services.py
                result = send_invoice_to_ksef(invoice.id)

                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                    self.message_user(
                        request,
                        f"Błąd przy fakturze {invoice.invoice_number}: {result['message']}",
                        level=messages.ERROR
                    )

            if success_count > 0:
                self.message_user(request, f"Pomyślnie wysłano {success_count} faktur do KSeF.", level=messages.SUCCESS)


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

        # Helper function to create a full name
        def info(model_name):
            return self.model._meta.app_label, self.model._meta.model_name

        my_urls = [
            path(
                "<int:object_id>/change/generate-pdf/",
                self.admin_site.admin_view(self.generate_pdf_view),
                name="%s_%s_pdf" % info(self.model),
            ),
            path(
                "import-jpk/",
                self.admin_site.admin_view(self.import_jpk_view),
                name="%s_%s_import_jpk" % info(self.model),
            ),
            path(
                "export-jpk/",
                self.admin_site.admin_view(self.export_jpk_view),
                name="%s_%s_export_jpk" % info(self.model),
            ),
            path(
                "send-ksef/",
                self.admin_site.admin_view(self.send_to_ksef_view),
                name="%s_%s_send_ksef" % info(self.model),
            ),
            path(
                "payments-report/",
                self.admin_site.admin_view(self.payments_report_view),
                name="%s_%s_payments_report" % info(self.model),
            ),
            path(
                "overdue-report/",
                self.admin_site.admin_view(self.overdue_report_view),
                name="%s_%s_overdue_report" % info(self.model),
            ),
        ]
        return my_urls + urls

    def payments_report_view(self, request):
        """Raport płatności"""
        today = timezone.now().date()

        # Statystyki płatności
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

        # Najnowsze płatności
        recent_payments = (
            Payment.objects.filter(user=request.user)
            .select_related("invoice", "invoice__contractor")
            .order_by("-payment_date")[:10]
        )

        # Przeterminowane faktury
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

        # Grupuj po okresach przeterminowania
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
                print(f"Błąd tworzenia pozycji faktury: {str(e)}")
                continue
        return items_created

    def generate_pdf_view(self, request, object_id):
        from weasyprint import HTML  # Import wewnątrz metody

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
    list_display = ("year", "month", "total_revenue", "income_tax_payable", "user")
    list_filter = ("year", "month", "user")
    search_fields = ("year", "month")
    readonly_fields = ("created_at",)
    exclude = ("user",)

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
                if xml_file.size > 50 * 1024 * 1024:  # 50MB
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

                # Bardziej szczegółowy komunikat o sukcesie
                if created_count or updated_count:
                    msg = f"Import zakończony pomyślnie. Utworzono: {created_count}, zaktualizowano: {updated_count} rozliczeń."
                    messages.success(request, msg)
                else:
                    messages.info(
                        request, "Nie znaleziono nowych danych do importu w pliku."
                    )

                # Dodawanie ostrzeżeń za pomocą messages framework
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

    # Nowa metoda do parsowania pliku JPK_EWP
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
            namespaces = {"tns": "http://jpk.mf.gov.pl/wzor/2022/02/01/02011/"}
            ewp_wiersze = root.findall("tns:EWPWiersz", namespaces)

            if not ewp_wiersze:
                raise ValueError("Nie znaleziono żadnych wpisów w pliku JPK_EWP.")

            monthly_revenues = {}
            for wiersz in ewp_wiersze:
                date_str = wiersz.find("tns:K_2", namespaces).text
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                year_month = (date.year, date.month)

                revenue = Decimal(wiersz.find("tns:K_7", namespaces).text) + Decimal(
                    wiersz.find("tns:K_11", namespaces).text
                )

                if year_month not in monthly_revenues:
                    monthly_revenues[year_month] = Decimal("0.00")
                monthly_revenues[year_month] += revenue

            created_count = 0
            updated_count = 0
            import_warnings = []
            updated_settlements_exist = False

            for (year, month), total_revenue in monthly_revenues.items():
                settlement, created = MonthlySettlement.objects.update_or_create(
                    user=user,
                    year=year,
                    month=month,
                    defaults={
                        "total_revenue": total_revenue,
                        "health_insurance_paid": 0,
                        "social_insurance_paid": 0,
                        "labor_fund_paid": 0,
                        "income_tax_payable": 0,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            warnings = []
            if created_count or updated_count:
                warnings.append(
                    "Pamiętaj, aby uzupełnić informacje o zapłaconych składkach ZUS (zdrowotne, społeczne, fundusz pracy) dla zaimportowanych miesięcy."
                )

            return created_count, updated_count, warnings
        except ET.ParseError as e:
            raise ValueError(f"Błąd parsowania XML: {str(e)}")

    def dashboard_view(self, request):
        """Dashboard z integracją rozliczenia rocznego i płatności"""

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

        # === DANE ROZLICZENIA ROCZNEGO ===
        current_yearly_settlement = YearlySettlement.objects.filter(
            user=request.user, year=current_year
        ).first()

        # Oblicz aktualny stan w roku
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

        # Oblicz prognozowaną podstawę opodatkowania i podatek
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

        # === STATYSTYKI PŁATNOŚCI ===
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

        # === PORÓWNANIE Z POPRZEDNIM ROKIEM ===
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

        # === PROGRES ROKU PODATKOWEGO ===
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

        # === WYKRES PODSTAWY OPODATKOWANIA ===
        monthly_tax_base = []
        tax_base_labels = []

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

        # === WYKRES PORÓWNANIA LAT ===
        years_comparison = []
        comparison_labels = []

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

        # === WYKRES PRZYCHODÓW MIESIĘCZNYCH ===
        monthly_revenue = (
            Invoice.objects.filter(user=request.user, issue_date__gte=start_date)
            .annotate(month=TruncMonth("issue_date"))
            .values("month")
            .annotate(total=Sum("total_amount"))
            .order_by("month")
        )

        revenue_labels = []
        revenue_data = []
        for item in monthly_revenue:
            revenue_labels.append(item["month"].strftime("%Y-%m"))
            revenue_data.append(float(item["total"] or 0))

        context["revenue_chart"] = {
            "labels": json.dumps(revenue_labels),
            "data": json.dumps(revenue_data),
        }

        # === DANE DLA WYKRESU PŁATNOŚCI ===
        monthly_payments = (
            Payment.objects.filter(
                user=request.user, payment_date__gte=start_date, status="completed"
            )
            .annotate(month=TruncMonth("payment_date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )

        payments_labels = []
        payments_data = []
        for item in monthly_payments:
            payments_labels.append(item["month"].strftime("%Y-%m"))
            payments_data.append(float(item["total"] or 0))

        # === STATYSTYKI STATUSÓW PŁATNOŚCI ===
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

        # Ostatnie faktury
        recent_invoices = Invoice.objects.filter(user=request.user).order_by(
            "-issue_date"
        )[:5]
        context["recent_invoices"] = recent_invoices

        # Miesięczne rozliczenia do sprawdzenia
        pending_settlements = []
        for month in range(1, 13):
            if not MonthlySettlement.objects.filter(
                user=request.user, year=current_year, month=month
            ).exists():
                if month <= datetime.now().month:
                    pending_settlements.append(month)

        context["pending_settlements"] = pending_settlements

        # === TERMINY I PRZYPOMNIENIA ===
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

        if datetime.now().month <= 3:
            if not YearlySettlement.objects.filter(
                user=request.user, year=previous_year
            ).exists():
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

        # Dodaj do kontekstu
        context["payment_stats"] = payment_stats
        context["payments_chart"] = {
            "labels": json.dumps(payments_labels),
            "data": json.dumps(payments_data),
        }
        context["payment_status_stats"] = payment_status_stats
        context["reminders"] = reminders

        return render(request, "admin/enhanced_dashboard.html", context)

    def calculate_view(self, request):
        """Widok do obliczania rozliczenia miesięcznego"""

        context = {
            "opts": self.model._meta,
            "title": "Obliczanie Rozliczenia Miesięcznego",
        }

        current_year = datetime.now().year
        context["years"] = list(range(current_year - 5, current_year + 1))
        context["months"] = list(range(1, 13))

        company_info = CompanyInfo.objects.filter(user=request.user).first()
        context["company_info"] = company_info

        if company_info:
            try:
                zus_rates = ZUSRates.get_current_rates()
                if zus_rates:
                    calculated_rates = zus_rates.calculate_social_insurance(
                        company_info
                    )
                    context["calculated_rates"] = calculated_rates
                    context["zus_rates"] = zus_rates
            except Exception as e:
                context["zus_rates"] = None
                context["calculated_rates"] = None

        if request.method == "POST":
            try:
                month = int(request.POST.get("month"))
                year = int(request.POST.get("year"))

                health_insurance = Decimal(
                    request.POST.get("health_insurance_paid", "0").replace(",", ".")
                )
                social_insurance = Decimal(
                    request.POST.get("social_insurance_paid", "0").replace(",", ".")
                )
                labor_fund = Decimal(
                    request.POST.get("labor_fund_paid", "0").replace(",", ".")
                )

                total_revenue = Invoice.objects.filter(
                    user=request.user, issue_date__year=year, issue_date__month=month
                ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

                tax_base_revenue = total_revenue - social_insurance
                tax_base_after_health = tax_base_revenue - (health_insurance / 2)
                if tax_base_after_health < 0:
                    tax_base_after_health = Decimal("0.00")

                income_tax_payable = round(tax_base_after_health * Decimal("0.14"))

                settlement, created = MonthlySettlement.objects.update_or_create(
                    user=request.user,
                    year=year,
                    month=month,
                    defaults={
                        "total_revenue": total_revenue,
                        "health_insurance_paid": health_insurance,
                        "social_insurance_paid": social_insurance,
                        "labor_fund_paid": labor_fund,
                        "income_tax_payable": income_tax_payable,
                    },
                )

                context["settlement"] = settlement
                context["submitted"] = True

            except Exception as e:
                messages.error(request, f"Błąd podczas obliczania: {e}")

        return render(request, "ksiegowosc/settlement_form.html", context)

    def zus_calculator_view(self, request):
        """Widok kalkulatora składek ZUS"""
        context = {
            "opts": self.model._meta,
            "title": "Kalkulator składek ZUS",
            "current_year": timezone.now().year,
        }

        company_info = CompanyInfo.objects.filter(user=request.user).first()
        context["company_info"] = company_info

        try:
            zus_rates = ZUSRates.get_current_rates()
            context["zus_rates"] = zus_rates
        except:
            zus_rates = None
            context["zus_rates"] = None

        if company_info and zus_rates:
            annual_income = request.GET.get("annual_income")
            if annual_income:
                try:
                    annual_income = Decimal(annual_income)
                except:
                    annual_income = None

            calculated_rates = zus_rates.calculate_social_insurance(
                company_info, annual_income
            )
            context["calculated_rates"] = calculated_rates

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
            {
                "fields": ("total_yearly_revenue",),
                "classes": ("collapse",),
            },
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
        (
            "Dodatkowe",
            {
                "fields": ("notes", "created_at"),
                "classes": ("collapse",),
            },
        ),
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
        context = {
            "opts": self.model._meta,
            "title": "Obliczanie Rozliczenia Rocznego",
        }

        if request.method == "POST":
            year = int(request.POST.get("year"))
            tax_rate = Decimal(request.POST.get("tax_rate", "14.00"))
            notes = request.POST.get("notes", "")

            monthly_settlements = MonthlySettlement.objects.filter(
                user=request.user, year=year
            ).order_by("month")

            if not monthly_settlements.exists():
                messages.error(
                    request,
                    f"Brak rozliczeń miesięcznych za rok {year}. Najpierw utwórz rozliczenia miesięczne.",
                )
                current_year = datetime.now().year
                context.update({"years": range(current_year - 5, current_year + 1)})
                return render(
                    request, "ksiegowosc/yearly_settlement_form.html", context
                )

            yearly_totals = monthly_settlements.aggregate(
                total_revenue=Sum("total_revenue"),
                total_social=Sum("social_insurance_paid"),
                total_health=Sum("health_insurance_paid"),
                total_labor=Sum("labor_fund_paid"),
                total_monthly_tax=Sum("income_tax_payable"),
            )

            total_yearly_revenue = yearly_totals["total_revenue"] or Decimal("0.00")
            total_social_insurance = yearly_totals["total_social"] or Decimal("0.00")
            total_health_insurance = yearly_totals["total_health"] or Decimal("0.00")
            total_labor_fund = yearly_totals["total_labor"] or Decimal("0.00")
            total_monthly_tax_paid = yearly_totals["total_monthly_tax"] or Decimal(
                "0.00"
            )

            tax_base = total_yearly_revenue - total_social_insurance
            tax_base_after_health = tax_base - (total_health_insurance / 2)
            if tax_base_after_health < 0:
                tax_base_after_health = Decimal("0.00")

            calculated_yearly_tax = (tax_base_after_health * tax_rate / 100).quantize(
                Decimal("0.01")
            )
            tax_difference = calculated_yearly_tax - total_monthly_tax_paid

            yearly_settlement, created = YearlySettlement.objects.update_or_create(
                user=request.user,
                year=year,
                defaults={
                    "total_yearly_revenue": total_yearly_revenue,
                    "total_social_insurance_paid": total_social_insurance,
                    "total_health_insurance_paid": total_health_insurance,
                    "total_labor_fund_paid": total_labor_fund,
                    "total_monthly_tax_paid": total_monthly_tax_paid,
                    "calculated_yearly_tax": calculated_yearly_tax,
                    "tax_difference": tax_difference,
                    "tax_rate_used": tax_rate,
                    "notes": notes,
                },
            )

            context["yearly_settlement"] = yearly_settlement
            context["monthly_settlements"] = monthly_settlements
            context["submitted"] = True
            context["created"] = created

        current_year = datetime.now().year
        context.update(
            {
                "years": range(current_year - 5, current_year + 1),
                "default_tax_rate": "14.00",
            }
        )
        return render(request, "ksiegowosc/yearly_settlement_form.html", context)

    def generate_yearly_pdf_view(self, request, object_id):
        from weasyprint import HTML  # Import wewnątrz metody

        """Generuje PDF z rozliczeniem rocznym"""
        queryset = self.get_queryset(request)
        try:
            yearly_settlement = queryset.get(pk=object_id)
        except YearlySettlement.DoesNotExist:
            messages.error(
                request,
                "Rozliczenie roczne nie zostało znalezione lub nie masz do niego uprawnień.",
            )
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))

        company_info = CompanyInfo.objects.filter(user=request.user).first()
        if not company_info:
            messages.error(
                request,
                "Nie można wygenerować PDF. Uzupełnij najpierw dane firmy w panelu.",
            )
            return redirect(request.META.get("HTTP_REFERER", "/admin/"))

        monthly_settlements = MonthlySettlement.objects.filter(
            user=request.user, year=yearly_settlement.year
        ).order_by("month")

        html_string = render_to_string(
            "ksiegowosc/yearly_settlement_pdf_template.html",
            {
                "yearly_settlement": yearly_settlement,
                "company_info": company_info,
                "monthly_settlements": monthly_settlements,
            },
        )

        html = HTML(string=html_string)
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type="application/pdf")
        filename = f"rozliczenie-roczne-{yearly_settlement.year}_{company_info.company_name.replace(' ', '_')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def view_yearly_settlement(self, request, object_id):
        """Wyświetla pełny podgląd rozliczenia rocznego"""
        queryset = self.get_queryset(request)
        try:
            yearly_settlement = queryset.get(pk=object_id)
        except YearlySettlement.DoesNotExist:
            messages.error(
                request,
                "Rozliczenie roczne nie zostało znalezione lub nie masz do niego uprawnień.",
            )
            return redirect("admin:ksiegowosc_yearlysettlement_changelist")

        monthly_settlements = MonthlySettlement.objects.filter(
            user=request.user, year=yearly_settlement.year
        ).order_by("month")

        context = {
            "opts": self.model._meta,
            "title": f"Podgląd rozliczenia rocznego {yearly_settlement.year}",
            "yearly_settlement": yearly_settlement,
            "monthly_settlements": monthly_settlements,
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
            ),
        ]
        return my_urls + urls

    def update_rates_view(self, request):
        """Widok do ręcznej aktualizacji stawek ZUS"""
        from django.core.management import call_command
        from io import StringIO

        if request.method == "POST":
            try:
                out = StringIO()
                call_command("update_zus_rates", "--force", stdout=out)
                output = out.getvalue()

                messages.success(
                    request, f"Stawki ZUS zostały zaktualizowane!\n{output}"
                )
            except Exception as e:
                messages.error(request, f"Błąd aktualizacji: {str(e)}")

        return redirect("admin:ksiegowosc_zusrates_changelist")


# ==== PURCHASE INVOICE ADMIN ====


@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
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
        status = obj.payment_status
        colors = {
            "paid": "green",
            "overdue": "red",
            "pending": "orange",
        }
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


# ==== EXPENSE CATEGORY ADMIN ====


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
