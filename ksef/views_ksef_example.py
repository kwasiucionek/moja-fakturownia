# ksiegowosc/views.py - przykładowe widoki KSeF

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST

from .models import Invoice
from ksef.services import KsefService, KsefServiceError


@login_required
@require_POST
def send_invoice_to_ksef(request, invoice_id):
    """
    Wysyła pojedynczą fakturę do KSeF.
    
    URL: /invoices/<id>/send-ksef/
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    
    if invoice.ksef_status in ['sent', 'confirmed']:
        messages.warning(request, f"Faktura {invoice.number} już wysłana do KSeF.")
        return redirect('invoice_detail', invoice_id=invoice.id)
    
    try:
        service = KsefService(request.user)
        result = service.send_invoice(invoice)
        
        messages.success(
            request,
            f"Faktura {invoice.number} wysłana do KSeF. "
            f"Numer ref: {result['invoice_reference']}"
        )
        
    except KsefServiceError as e:
        messages.error(request, f"Błąd wysyłki do KSeF: {e}")
    
    return redirect('invoice_detail', invoice_id=invoice.id)


@login_required
def send_invoice_to_ksef_ajax(request, invoice_id):
    """
    Wysyła fakturę do KSeF (AJAX).
    
    URL: /api/invoices/<id>/send-ksef/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    
    if invoice.ksef_status in ['sent', 'confirmed']:
        return JsonResponse({
            'success': False,
            'error': 'Faktura już wysłana'
        })
    
    try:
        service = KsefService(request.user)
        result = service.send_invoice(invoice)
        
        return JsonResponse({
            'success': True,
            'invoice_reference': result['invoice_reference'],
            'session_reference': result['session_reference'],
        })
        
    except KsefServiceError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def check_invoice_ksef_status(request, invoice_id):
    """
    Sprawdza status faktury w KSeF.
    
    URL: /api/invoices/<id>/ksef-status/
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    
    if not invoice.ksef_reference:
        return JsonResponse({
            'error': 'Faktura nie wysłana do KSeF'
        }, status=400)
    
    try:
        service = KsefService(request.user)
        status = service.get_invoice_status(invoice.ksef_reference)
        
        return JsonResponse(status)
        
    except KsefServiceError as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def download_upo(request, invoice_id):
    """
    Pobiera UPO (Urzędowe Poświadczenie Odbioru).
    
    URL: /invoices/<id>/upo/
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    
    if not invoice.ksef_reference:
        messages.error(request, "Faktura nie wysłana do KSeF.")
        return redirect('invoice_detail', invoice_id=invoice.id)
    
    try:
        service = KsefService(request.user)
        upo_content = service.download_upo(invoice.ksef_reference)
        
        response = HttpResponse(
            upo_content,
            content_type='application/pdf'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="UPO_{invoice.number}.pdf"'
        )
        return response
        
    except KsefServiceError as e:
        messages.error(request, f"Błąd pobierania UPO: {e}")
        return redirect('invoice_detail', invoice_id=invoice.id)


# === URLs (do urls.py) ===
"""
from django.urls import path
from . import views

urlpatterns = [
    # ... inne URL-e ...
    
    # KSeF
    path(
        'invoices/<int:invoice_id>/send-ksef/', 
        views.send_invoice_to_ksef, 
        name='send_invoice_to_ksef'
    ),
    path(
        'invoices/<int:invoice_id>/upo/', 
        views.download_upo, 
        name='download_upo'
    ),
    
    # API
    path(
        'api/invoices/<int:invoice_id>/send-ksef/', 
        views.send_invoice_to_ksef_ajax, 
        name='send_invoice_to_ksef_ajax'
    ),
    path(
        'api/invoices/<int:invoice_id>/ksef-status/', 
        views.check_invoice_ksef_status, 
        name='check_invoice_ksef_status'
    ),
]
"""
