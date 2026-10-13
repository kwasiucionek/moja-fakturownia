# ksiegowosc/admin.py - fragment do dodania
# Akcje admin do wysyłania faktur do KSeF

from django.contrib import admin, messages
from django.utils.html import format_html

from ksef.services import KsefService, KsefServiceError


class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'number', 'issue_date', 'client_name', 'total_gross', 
        'ksef_status_display', 'ksef_reference'
    ]
    list_filter = ['ksef_status', 'issue_date']
    readonly_fields = [
        'ksef_reference', 'ksef_session_reference', 
        'ksef_sent_at', 'ksef_number'
    ]
    actions = ['send_to_ksef', 'send_batch_to_ksef']
    
    def ksef_status_display(self, obj):
        """Kolorowy status KSeF."""
        colors = {
            'draft': 'gray',
            'pending': 'orange', 
            'sent': 'blue',
            'confirmed': 'green',
            'error': 'red',
        }
        color = colors.get(obj.ksef_status, 'gray')
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_ksef_status_display()
        )
    ksef_status_display.short_description = 'Status KSeF'
    
    @admin.action(description="Wyślij wybrane faktury do KSeF (pojedynczo)")
    def send_to_ksef(self, request, queryset):
        """Wysyła każdą fakturę osobno."""
        success_count = 0
        error_count = 0
        
        try:
            service = KsefService(request.user)
        except KsefServiceError as e:
            self.message_user(request, f"Błąd inicjalizacji: {e}", messages.ERROR)
            return
        
        for invoice in queryset:
            if invoice.ksef_status in ['sent', 'confirmed']:
                self.message_user(
                    request, 
                    f"Faktura {invoice.number} już wysłana.", 
                    messages.WARNING
                )
                continue
                
            try:
                result = service.send_invoice(invoice)
                success_count += 1
            except KsefServiceError as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Błąd faktury {invoice.number}: {e}",
                    messages.ERROR
                )
        
        if success_count:
            self.message_user(
                request,
                f"Wysłano {success_count} faktur do KSeF.",
                messages.SUCCESS
            )
    
    @admin.action(description="Wyślij wybrane faktury do KSeF (batch)")
    def send_batch_to_ksef(self, request, queryset):
        """Wysyła wszystkie faktury w jednej sesji - szybsze."""
        invoices = list(queryset.exclude(ksef_status__in=['sent', 'confirmed']))
        
        if not invoices:
            self.message_user(
                request,
                "Brak faktur do wysłania.",
                messages.WARNING
            )
            return
        
        try:
            service = KsefService(request.user)
            results = service.send_multiple_invoices(invoices)
            
            success = sum(1 for r in results if r['success'])
            errors = sum(1 for r in results if not r['success'])
            
            if success:
                self.message_user(
                    request,
                    f"Wysłano {success} faktur do KSeF.",
                    messages.SUCCESS
                )
            if errors:
                self.message_user(
                    request,
                    f"Błędy dla {errors} faktur.",
                    messages.ERROR
                )
                
        except KsefServiceError as e:
            self.message_user(request, f"Błąd: {e}", messages.ERROR)
