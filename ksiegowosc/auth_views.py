# ksiegowosc/auth_views.py

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .auth_forms import CustomUserCreationForm, UserProfileForm
from .models import CompanyInfo
import logging

logger = logging.getLogger(__name__)


@sensitive_post_parameters()
@csrf_protect
@never_cache
def register_view(request):
    """Widok rejestracji nowego użytkownika"""
    
    if request.user.is_authenticated:
        messages.info(request, 'Jesteś już zalogowany.')
        return redirect('admin:index')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                
                # Automatyczne logowanie po rejestracji
                username = form.cleaned_data.get('username')
                password = form.cleaned_data.get('password1')
                user = authenticate(username=username, password=password)
                
                if user:
                    login(request, user)
                    
                    # Utwórz podstawową informację o firmie jeśli podano nazwę
                    company_name = form.cleaned_data.get('company_name')
                    if company_name:
                        try:
                            CompanyInfo.objects.create(
                                user=user,
                                company_name=company_name,
                                tax_id='',  # Do uzupełnienia później
                                street='',
                                zip_code='',
                                city='',
                                bank_account_number=''
                            )
                        except Exception as e:
                            logger.warning(f"Nie udało się utworzyć CompanyInfo dla {user.username}: {e}")
                    
                    messages.success(
                        request, 
                        f'Witaj {user.first_name}! Twoje konto zostało utworzone. '
                        'Uzupełnij teraz dane swojej firmy.'
                    )
                    
                    # Przekieruj do uzupełnienia danych firmy
                    if CompanyInfo.objects.filter(user=user).exists():
                        return redirect('admin:ksiegowosc_companyinfo_changelist')
                    else:
                        return redirect('admin:ksiegowosc_companyinfo_add')
                
            except Exception as e:
                logger.error(f"Błąd podczas rejestracji użytkownika: {e}")
                messages.error(request, 'Wystąpił błąd podczas tworzenia konta. Spróbuj ponownie.')
        
        else:
            # Dodaj błędy formularza do messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    else:
        form = CustomUserCreationForm()
    
    context = {
        'form': form,
        'title': 'Rejestracja nowego konta'
    }
    return render(request, 'auth/register.html', context)


@login_required
def profile_view(request):
    """Widok profilu użytkownika"""
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil został zaktualizowany.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    # Pobierz informacje o firmie
    company_info = None
    try:
        company_info = CompanyInfo.objects.get(user=request.user)
    except CompanyInfo.DoesNotExist:
        pass
    
    context = {
        'form': form,
        'company_info': company_info,
        'title': 'Mój profil'
    }
    return render(request, 'auth/profile.html', context)


@login_required
def dashboard_redirect(request):
    """Przekierowanie na odpowiedni dashboard po logowaniu"""
    
    # Sprawdź czy użytkownik ma dane firmy
    if not CompanyInfo.objects.filter(user=request.user).exists():
        messages.warning(
            request, 
            'Uzupełnij najpierw podstawowe dane swojej firmy, aby móc korzystać z systemu.'
        )
        return redirect('admin:ksiegowosc_companyinfo_add')
    
    # Przekieruj na dashboard
    return redirect('admin:ksiegowosc_dashboard')


def terms_view(request):
    """Widok regulaminu"""
    context = {
        'title': 'Regulamin serwisu'
    }
    return render(request, 'auth/terms.html', context)


def privacy_view(request):
    """Widok polityki prywatności"""
    context = {
        'title': 'Polityka prywatności'
    }
    return render(request, 'auth/privacy.html', context)


class RegisterView(CreateView):
    """Alternatywny widok rejestracji oparty na klasach"""
    
    form_class = CustomUserCreationForm
    template_name = 'auth/register.html'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('admin:index')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Automatyczne logowanie
        user = authenticate(
            username=form.cleaned_data['username'],
            password=form.cleaned_data['password1']
        )
        if user:
            login(self.request, user)
            messages.success(
                self.request,
                f'Witaj {user.first_name}! Twoje konto zostało utworzone.'
            )
        
        return response
    
    def get_success_url(self):
        return reverse('admin:ksiegowosc_companyinfo_add')


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Widok edycji profilu oparty na klasach"""
    
    model = User
    form_class = UserProfileForm
    template_name = 'auth/profile_edit.html'
    
    def get_object(self):
        return self.request.user
    
    def form_valid(self, form):
        messages.success(self.request, 'Profil został zaktualizowany.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('profile')
