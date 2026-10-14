# ksiegowosc/auth_forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

from .permissions import grant_default_access
from django.core.exceptions import ValidationError
import re


class CustomAuthenticationForm(AuthenticationForm):
    """Custom login form z Bootstrap CSS"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Nazwa użytkownika lub email'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Hasło'
        })


class CustomUserCreationForm(UserCreationForm):
    """Formularz rejestracji użytkownika z dodatkowymi polami"""
    
    email = forms.EmailField(
        required=True,
        help_text='Wymagany. Wprowadź prawidłowy adres email.',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'twoj@email.com'
        })
    )
    
    first_name = forms.CharField(
        max_length=30,
        required=True,
        help_text='Wymagane.',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Imię'
        })
    )
    
    last_name = forms.CharField(
        max_length=30,
        required=True,
        help_text='Wymagane.',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nazwisko'
        })
    )
    
    company_name = forms.CharField(
        max_length=255,
        required=False,
        help_text='Opcjonalne. Nazwa firmy (możesz uzupełnić później).',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nazwa firmy (opcjonalnie)'
        })
    )
    
    terms_accepted = forms.BooleanField(
        required=True,
        help_text='Musisz zaakceptować regulamin.',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nazwa użytkownika'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dodaj klasy CSS do pól hasła
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Hasło'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Potwierdź hasło'
        })

    def clean_email(self):
        """Sprawdź czy email jest unikalny"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("Użytkownik z tym adresem email już istnieje.")
        return email

    def clean_username(self):
        """Sprawdź username"""
        username = self.cleaned_data.get('username')
        
        # Sprawdź czy zawiera tylko dozwolone znaki
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            raise ValidationError(
                "Nazwa użytkownika może zawierać tylko litery, cyfry, kropki, podkreślenia i myślniki."
            )
        
        # Sprawdź długość
        if len(username) < 3:
            raise ValidationError("Nazwa użytkownika musi mieć co najmniej 3 znaki.")
        
        return username

    def save(self, commit=True):
        """Zapisz użytkownika i przypisz do grupy 'ksiegowosc'"""
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_staff = True  # Dostęp do panelu admina
        
        if commit:
            user.save()
            # Grupa „ksiegowosc” z uprawnieniami (ksiegowosc/permissions.py)
            grant_default_access(user)

        return user


class UserProfileForm(forms.ModelForm):
    """Formularz edycji profilu użytkownika"""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Imię'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nazwisko'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email'
            }),
        }

    def clean_email(self):
        """Sprawdź czy email jest unikalny (z wyłączeniem bieżącego użytkownika)"""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Użytkownik z tym adresem email już istnieje.")
        return email