# ksiegowosc/auth_urls.py

from django.urls import path, include
from django.contrib.auth import views as django_auth_views
from . import auth_views
from .auth_forms import CustomAuthenticationForm

app_name = 'auth'

urlpatterns = [
    # Rejestracja
    path('register/', auth_views.register_view, name='register'),
    path('register-class/', auth_views.RegisterView.as_view(), name='register_class'),
    
    # Logowanie i wylogowanie
    path('login/', auth_views.LoginView.as_view(
        template_name='auth/login.html',
        authentication_form=CustomAuthenticationForm,
        redirect_authenticated_user=True,
        extra_context={'title': 'Logowanie'}
    ), name='login'),
    
    path('logout/', auth_views.LogoutView.as_view(
        next_page='auth:login'
    ), name='logout'),
    
    # Profil użytkownika
    path('profile/', auth_views.profile_view, name='profile'),
    path('profile/edit/', auth_views.ProfileUpdateView.as_view(), name='profile_edit'),
    
    # Reset hasła
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset.html',
        email_template_name='auth/password_reset_email.html',
        subject_template_name='auth/password_reset_subject.txt',
        success_url='/auth/password-reset/done/',
        extra_context={'title': 'Reset hasła'}
    ), name='password_reset'),
    
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html',
        extra_context={'title': 'Reset hasła wysłany'}
    ), name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html',
        success_url='/auth/reset/done/',
        extra_context={'title': 'Nowe hasło'}
    ), name='password_reset_confirm'),
    
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html',
        extra_context={'title': 'Hasło zmienione'}
    ), name='password_reset_complete'),
    
    # Zmiana hasła dla zalogowanych użytkowników
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='auth/password_change.html',
        success_url='/auth/password-change/done/',
        extra_context={'title': 'Zmiana hasła'}
    ), name='password_change'),
    
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='auth/password_change_done.html',
        extra_context={'title': 'Hasło zmienione'}
    ), name='password_change_done'),
    
    # Przekierowania
    path('dashboard/', auth_views.dashboard_redirect, name='dashboard'),
    
    # Strony informacyjne
    path('terms/', auth_views.terms_view, name='terms'),
    path('privacy/', auth_views.privacy_view, name='privacy'),
    
    # Google OAuth (jeśli włączone)
    path('social-auth/', include('social_django.urls', namespace='social')),
]