# ksiegowosc/admin.py

from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import CompanyInfo, Contractor, Invoice, InvoiceItem, MonthlySettlement
from django.contrib import messages
from django.shortcuts import redirect

# Imports for django-import-export and custom logic
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget
from .formats import JPKXMLFormat # Our custom format

# Other necessary imports
from datetime import datetime
from decimal import Decimal
from django.db.models import Sum

# --- Custom Widget for looking up Contractors by NIP for the current user ---
class ContractorWidget(ForeignKeyWidget):
    def __init__(self, user, **kwargs):
        self.user = user
        # We tell the widget to look up Contractor objects using the 'tax_id' field
        super().__init__(Contractor, 'tax_id', **kwargs)

    def clean(self, value, row=None, *args, **kwargs):
        # This method finds or creates a contractor based on the NIP from the imported file
        if not value:
            return None

        # get_or_create ensures we don't create duplicate contractors for the same user and NIP
        contractor, _ = Contractor.objects.get_or_create(
            tax_id=value,
            user=self.user,
            defaults={'name': row.get('contractor_name', 'Brak nazwy')}
        )
        return contractor

# --- Resource for defining how Invoices are imported/exported ---
class InvoiceResource(resources.ModelResource):
    # We define each column to be imported and tell it how to handle it
    contractor = Field(
        attribute='contractor',
        column_name='contractor_tax_id',
        widget=None # The widget will be set dynamically in __init__
    )
    # This is a helper column used by the widget, not saved to the model directly
    contractor_name = Field(attribute='contractor_name', column_name='contractor_name')

    class Meta:
        model = Invoice
        # Fields to use for standard import/export (CSV, XLSX, etc.)
        fields = ('id', 'invoice_number', 'issue_date', 'sale_date', 'total_amount', 'user', 'contractor', 'contractor_name')
        export_order = fields
        # Use invoice_number as the unique key to prevent creating duplicate invoices
        import_id_fields = ('invoice_number',)
        skip_unchanged = True
        report_skipped = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize the widget with a placeholder user; it will be updated with the real user later
        self.fields['contractor'].widget = ContractorWidget(user=None)

    def before_import(self, dataset, using_transactions, user, **kwargs):
        """
        This hook runs before the main import. We pass the current user to the instance.
        """
        self.user = user
        self.fields['contractor'].widget.user = self.user

        # If the file is XML, we use our custom JPK parser (from formats.py) to create the dataset
        if kwargs.get('file_name', '').lower().endswith('.xml'):
            # The actual conversion happens in the JPKXMLFormat class
            # This hook is a good place for any additional pre-processing if needed
            pass

    def before_save_instance(self, instance, using_transactions, dry_run):
        """Assigns the logged-in user to each imported object before it's saved."""
        if self.user:
            instance.user = self.user

# --- ModelAdmin Classes ---

@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'tax_id', 'user')
    exclude = ('user',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)

@admin.register(Contractor)
class ContractorAdmin(ImportExportModelAdmin):
    list_display = ('name', 'tax_id', 'city', 'user')
    search_fields = ('name', 'tax_id')
    exclude = ('user',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)

@admin.register(MonthlySettlement)
class MonthlySettlementAdmin(admin.ModelAdmin):
    change_list_template = "admin/ksiegowosc/monthlysettlement/change_list.html"
    list_display = ('year', 'month', 'total_revenue', 'income_tax_payable', 'user')
    list_filter = ('year', 'user')
    exclude = ('user',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('oblicz/', self.admin_site.admin_view(self.calculate_view), name='ksiegowosc_monthlysettlement_calculate')]
        return my_urls + urls

    def calculate_view(self, request):
        context = {'opts': self.model._meta, 'site_header': 'Fakturownia', 'site_title': 'Panel Admina', 'title': 'Obliczanie Rozliczenia Miesięcznego'}
        if request.method == 'POST':
            month, year = int(request.POST.get('month')), int(request.POST.get('year'))
            health_insurance_paid = float(request.POST.get('health_insurance_paid', '0').replace(',', '.'))
            total_revenue = Invoice.objects.filter(user=request.user, issue_date__year=year, issue_date__month=month).aggregate(total=Sum('total_amount'))['total'] or 0.00
            tax_base = float(total_revenue) - (health_insurance_paid * 0.5)
            if tax_base < 0: tax_base = 0
            income_tax_payable = round(tax_base * 0.14)
            settlement, _ = MonthlySettlement.objects.update_or_create(user=request.user, year=year, month=month, defaults={'total_revenue': total_revenue, 'health_insurance_paid': health_insurance_paid, 'income_tax_payable': income_tax_payable})
            context.update({'settlement': settlement, 'submitted': True})
        current_year = datetime.now().year
        context.update({'years': range(current_year - 5, current_year + 1), 'months': range(1, 13)})
        return render(request, 'ksiegowosc/settlement_form.html', context)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ('total_price',)
    exclude = ('user',)

@admin.register(Invoice)
class InvoiceAdmin(ImportExportModelAdmin):
    resource_classes = [InvoiceResource]
    inlines = [InvoiceItemInline]
    list_display = ('invoice_number', 'contractor', 'issue_date', 'total_amount', 'is_correction', 'user')
    list_filter = ('issue_date', 'contractor', 'is_correction', 'user')
    search_fields = ('invoice_number', 'contractor__name')
    exclude = ('user',)

    def get_import_formats(self):
        """Adds our custom JPKXMLFormat to the list of available formats."""
        formats = super().get_import_formats()
        return [JPKXMLFormat] + formats

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "contractor" and not request.user.is_superuser:
            kwargs["queryset"] = Contractor.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        if not hasattr(obj, 'user') or not obj.user: obj.user = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not hasattr(instance, 'user') or not instance.user: instance.user = request.user
            instance.save()
        formset.save_m2m()

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('<int:object_id>/change/generate-pdf/', self.admin_site.admin_view(self.generate_pdf_view), name='ksiegowosc_invoice_pdf')]
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
        html_string = render_to_string('ksiegowosc/invoice_pdf_template.html', {'invoice': invoice, 'company_info': company_info})
        html = HTML(string=html_string)
        pdf = html.write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="faktura-{invoice.invoice_number.replace("/", "_")}.pdf"'
        return response
