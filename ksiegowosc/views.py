# ksiegowosc/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from django.db import transaction
from .forms import InvoiceForm, InvoiceItemFormSet
from django.db.models import Sum
from datetime import datetime
from .models import Invoice, CompanyInfo, MonthlySettlement, Contractor, InvoiceItem
import re
import subprocess
from io import BytesIO
from decimal import Decimal, InvalidOperation
from django.core.files.base import ContentFile
import base64
import xml.etree.ElementTree as ET
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required

@login_required
def invoice_list(request):
    """Widok listy wszystkich faktur."""
    invoices = Invoice.objects.all()
    context = {'invoices': invoices}
    return render(request, 'ksiegowosc/invoice_list.html', context)

def invoice_detail(request, invoice_id):
    """Widok szczegółów pojedynczej faktury."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    context = {'invoice': invoice}
    return render(request, 'ksiegowosc/invoice_detail.html', context)


def invoice_create(request):
    """Widok do tworzenia nowej faktury z pozycjami."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Zapisujemy główną fakturę
                    invoice = form.save(commit=False)
                    invoice.save() # Zapisz, aby uzyskać ID

                    # Przypisujemy fakturę do pozycji i zapisujemy je
                    formset.instance = invoice
                    formset.save()

                    # Generujemy numer faktury po jej zapisaniu
                    invoice.invoice_number = f"F/{invoice.id}/{invoice.issue_date.strftime('%m/%Y')}"
                    # Jeśli w sesji jest plik PDF z importu, dołącz go i wyczyść sesję
                    if 'pdf_import_content_b64' in request.session:
                        pdf_base64 = request.session.pop('pdf_import_content_b64')
                        pdf_content = base64.b64decode(pdf_base64) # Odkodowujemy z Base64
                        file_name = f"import_{invoice.invoice_number.replace('/', '_')}.pdf"
                        invoice.original_pdf.save(file_name, ContentFile(pdf_content))

                    invoice.save()

                return redirect('invoice_detail', invoice_id=invoice.id)
            except Exception as e:
                # Tutaj można dodać logowanie błędu
                print(e)
    else:
        form = InvoiceForm()
        formset = InvoiceItemFormSet()

    context = {
        'form': form,
        'formset': formset,
    }
    return render(request, 'ksiegowosc/invoice_form.html', context)
