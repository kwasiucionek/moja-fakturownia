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

# Importy usług KSeF - upewnij się, że w tych plikach nie ma importów z ksiegowosc.models na górze!
from ksef.client import KsefClient
from ksef.services import send_invoice_to_ksef
from ksef.xml_generator import generate_invoice_xml

# Standardowy import modeli. Jeśli ksef.* nie importują niczego na górze, to nie będzie błędu.
from .models import (
    CompanyInfo,
    Contractor,
    ExpenseCategory,
    Invoice,
    InvoiceItem,
    MonthlySettlement,
    Payment,
    PurchaseInvoice,
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
            return queryset.annotate(paid_sum=Sum("payments__amount")).filter(paid_sum__gte=F("total_amount")).distinct()
        elif self.value() == "partial":
            return queryset.annotate(paid_sum=Sum("payments__amount")).filter(paid_sum__gt=0, paid_sum__lt=F("total_amount")).distinct()
        elif self.value() == "overdue":
            return queryset.filter(payment_date__lt=today).annotate(paid_sum=Sum("payments__amount")).exclude(paid_sum__gte=F("total_amount")).distinct()
        elif self.value() == "unpaid":
            return queryset.filter(payments__isnull=True).distinct()
        return queryset

# ==== COMPANY INFO ADMIN ====

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ("company_name", "tax_id", "business_type", "user")
    list_filter = ("business_type", "income_tax_type", "vat_settlement", "vat_payer", "zus_payer")
    search_fields = ("company_name", "tax_id", "regon", "krs")
    exclude = ("user",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)

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
        return qs if request.user.is_superuser else qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

# ==== PAYMENT ADMIN ====

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "contractor_name", "amount", "payment_date", "status", "user")
    autocomplete_fields = ["invoice"]
    exclude = ("user",)

    def invoice_number(self, obj):
        return obj.invoice.invoice_number
    invoice_number.short_description = "Numer faktury"

    def contractor_name(self, obj):
        return obj.invoice.contractor.name
    contractor_name.short_description = "Kontrahent"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)

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
    readonly_fields = ("total_price",)
    exclude = ("user",)

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    exclude = ("user",)

# ==== INVOICE ADMIN ====

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = [InvoiceItemInline, PaymentInline]
    list_display = ("invoice_number", "contractor", "issue_date", "total_amount", "payment_status_colored", "ksef_status_colored", "user")
    list_filter = ("issue_date", "is_correction", "ksef_status", "user", PaymentStatusFilter)
    search_fields = ("invoice_number", "contractor__name", "ksef_reference_number")
    actions = ["action_send_to_ksef"]

    def payment_status_colored(self, obj):
        colors = {"paid": "green", "partial": "orange", "overdue": "red", "unpaid": "gray"}
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', colors.get(obj.payment_status, "black"), obj.payment_status_display)
    payment_status_colored.short_description = "Status płatności"

    def ksef_status_colored(self, obj):
        if not obj.ksef_status: return "Brak"
        color = "green" if "przetworzono" in obj.ksef_status.lower() else "orange"
        if "błąd" in obj.ksef_status.lower(): color = "red"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.ksef_status)
    ksef_status_colored.short_description = "Status KSeF"

    @admin.action(description="Wyślij wybrane faktury do KSeF")
    def action_send_to_ksef(self, request, queryset):
        success_count = 0
        for invoice in queryset:
            result = send_invoice_to_ksef(invoice.id)
            if result["success"]: success_count += 1
            else: self.message_user(request, f"Błąd {invoice.invoice_number}: {result['message']}", level=messages.ERROR)
        if success_count: self.message_user(request, f"Wysłano {success_count} faktur.", level=messages.SUCCESS)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        my_urls = [
            path("<int:object_id>/generate-pdf/", self.admin_site.admin_view(self.generate_pdf_view), name="%s_%s_pdf" % info),
        ]
        return my_urls + urls

    def generate_pdf_view(self, request, object_id):
        from weasyprint import HTML
        invoice = self.get_queryset(request).get(pk=object_id)
        company_info = CompanyInfo.objects.filter(user=request.user).first()
        html_string = render_to_string("ksiegowosc/invoice_pdf_template.html", {"invoice": invoice, "company_info": company_info})
        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="faktura_{invoice.invoice_number}.pdf"'
        return response

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, "user") or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)

# ==== MONTHLY SETTLEMENT ADMIN ====

@admin.register(MonthlySettlement)
class MonthlySettlementAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "total_revenue", "income_tax_payable", "user")
    exclude = ("user",)

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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)

# ==== ZUS RATES ADMIN ====

@admin.register(ZUSRates)
class ZUSRatesAdmin(admin.ModelAdmin):
    list_display = ("year", "minimum_wage", "is_current")

# ==== PURCHASE INVOICE ADMIN ====

@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "supplier", "total_amount", "user")
    autocomplete_fields = ["supplier"]
    exclude = ("user",)

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
