from django import forms
from .models import Invoice, InvoiceItem

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['contractor', 'issue_date', 'sale_date', 'payment_method', 'payment_date', 'notes']
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'sale_date': forms.DateInput(attrs={'type': 'date'}),
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

# Tworzymy FormSet dla pozycji na fakturze powiązanych z fakturą
InvoiceItemFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceItem,
    fields=('name', 'quantity', 'unit', 'unit_price'),
    extra=1, # Domyślnie pokazuj 1 pusty formularz pozycji
    can_delete=True, # Pozwól na usuwanie pozycji
    widgets={
        'name': forms.TextInput(attrs={'class': 'form-control'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        'unit': forms.TextInput(attrs={'class': 'form-control'}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control'}),
    }
)
