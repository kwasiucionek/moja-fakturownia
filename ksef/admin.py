from django.contrib import messages
from ksef.client import KsefClient
from ksef.xml_generator import generate_invoice_xml
from django.utils import timezone


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    # ... (istniejąca konfiguracja)
    list_display = ('invoice_number', 'contractor', 'issue_date', 'total_amount', 'payment_status_colored', 'ksef_status', 'user') # Dodaj ksef_status
    list_filter = ('issue_date', 'contractor', 'is_correction', 'user', PaymentStatusFilter, 'ksef_status') # Dodaj ksef_status

    def send_to_ksef(self, request, queryset):
        # ... (poprzednia implementacja bez zmian)
        # Zmodyfikuj tylko fragment po wysyłce
            if response.get("processingStatus") == "ERROR":
                # ... (obsługa błędu bez zmian)
            else:
                session_id = response.get("elementReferenceNumber")
                invoice.ksef_status = 'Wysłano'
                invoice.ksef_session_id = session_id
                invoice.ksef_sent_at = timezone.now()
                invoice.ksef_processing_description = response.get("processingDescription")
                invoice.save()

                self.message_user(request, f"Faktura {invoice.invoice_number} wysłana. ID sesji: {session_id}. Sprawdź status za chwilę.", level=messages.SUCCESS)

    def check_ksef_status(self, request, queryset):
        """Nowa akcja do sprawdzania statusu faktur w KSeF."""
        for invoice in queryset.filter(ksef_status='Wysłano'):
            if not invoice.ksef_session_id:
                self.message_user(request, f"Faktura {invoice.invoice_number} nie ma zapisanego ID sesji.", level=messages.WARNING)
                continue

try:
                client = KsefClient(request.user)
                status = client.get_session_status(invoice.ksef_session_id)

                invoice.ksef_processing_description = status.get("processingDescription")

                if status.get("processingCode") == 315: # Przetwarzanie zakończone
                    invoice.ksef_status = "Przetworzono"

                    # === NOWA LOGIKA: POBIERANIE NUMERU KSEF ===
                    ksef_ref_number = status.get("elementReferenceNumber")
                    if ksef_ref_number:
                        invoice.ksef_reference_number = ksef_ref_number
                        self.message_user(request, f"Faktura {invoice.invoice_number}: Przetworzona! Numer KSeF: {ksef_ref_number}", level=messages.SUCCESS)
                    else:
                        self.message_user(request, f"Faktura {invoice.invoice_number}: Przetworzona, ale nie otrzymano numeru KSeF.", level=messages.WARNING)

                elif status.get("processingCode") >= 400: # Błędy
                    invoice.ksef_status = "Błąd"
                    self.message_user(request, f"Faktura {invoice.invoice_number}: Błąd przetwarzania - {status.get('processingDescription')}", level=messages.ERROR)
                else: # Nadal w toku
                    self.message_user(request, f"Faktura {invoice.invoice_number}: Nadal w trakcie przetwarzania.", level=messages.INFO)

                invoice.save()

            except Exception as e:
                self.message_user(request, f"Błąd sprawdzania statusu dla faktury {invoice.invoice_number}: {e}", level=messages.ERROR)

    check_ksef_status.short_description = "Sprawdź status zaznaczonych w KSeF"

    actions = ['send_to_ksef', 'check_ksef_status']
