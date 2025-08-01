# fakturownia/settings.py

"""
Django settings for fakturownia project - PRODUCTION READY
Generated by 'django-admin startproject' using Django 5.2.3.
"""

from pathlib import Path
import os
import environ
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environment variables
env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
    SECRET_KEY=(str, 'django-insecure-fallback-key-for-dev'),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    SECURE_SSL_REDIRECT=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0),
    SECURE_HSTS_INCLUDE_SUBDOMAINS=(bool, False),
    SECURE_HSTS_PRELOAD=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    # Ustawienie wartości domyślnej, aby uniknąć błędów
    SECURE_PROXY_SSL_HEADER=(bool, False)
)

# Take environment variables from .env file
environ.Env.read_env(BASE_DIR / '.env')

# =============================================================================
# SECURITY SETTINGS
# =============================================================================

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')
# KLUCZOWE: Poprawka błędu CSRF. Wczytywanie zaufanych domen z pliku .env.
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Security headers
SECURE_SSL_REDIRECT = env('SECURE_SSL_REDIRECT')
SECURE_HSTS_SECONDS = env('SECURE_HSTS_SECONDS')
SECURE_HSTS_INCLUDE_SUBDOMAINS = env('SECURE_HSTS_INCLUDE_SUBDOMAINS')
SECURE_HSTS_PRELOAD = env('SECURE_HSTS_PRELOAD')
SECURE_CONTENT_TYPE_NOSNIFF = env.bool('SECURE_CONTENT_TYPE_NOSNIFF', True)
SECURE_BROWSER_XSS_FILTER = env.bool('SECURE_BROWSER_XSS_FILTER', True)

# KLUCZOWE: Poprawna obsługa nagłówka od proxy (Cloudflare/mikr.us) dla HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if env('SECURE_PROXY_SSL_HEADER') else None

# Cookies security
SESSION_COOKIE_SECURE = env('SESSION_COOKIE_SECURE')
CSRF_COOKIE_SECURE = env('CSRF_COOKIE_SECURE')
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = env.int('SESSION_COOKIE_AGE', 28800)  # 8 godzin

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'social_django',
    'corsheaders',
    'django_extensions',
    *(['debug_toolbar'] if DEBUG else []),
    'ksiegowosc',
    'health_check',
    'health_check.db',
    'health_check.cache',
    'health_check.storage',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'ksiegowosc.middleware.AdminLoginRedirectMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    *(['debug_toolbar.middleware.DebugToolbarMiddleware'] if DEBUG else []),
    'social_django.middleware.SocialAuthExceptionMiddleware', # Ważne dla obsługi błędów OAuth
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'fakturownia.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
        },
    },
]

WSGI_APPLICATION = 'fakturownia.wsgi.application'

# =============================================================================
# DATABASE
# =============================================================================

DATABASES = {
    'default': env.db_url('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}
DATABASES['default']['CONN_MAX_AGE'] = env.int('DB_CONN_MAX_AGE', 600)
DATABASES['default']['CONN_HEALTH_CHECKS'] = env.bool('DB_CONN_HEALTH_CHECKS', True)


# =============================================================================
# AUTHENTICATION & SOCIAL AUTH (POPRAWIONA SEKCJA)
# =============================================================================

LOGIN_URL = 'auth:login'
LOGOUT_REDIRECT_URL = 'auth:login'
LOGIN_REDIRECT_URL = 'auth:dashboard'

AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

# KLUCZOWE: Cała konfiguracja Google Auth przeniesiona poza blok if DEBUG:
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = env('GOOGLE_OAUTH2_KEY', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env('GOOGLE_OAUTH2_SECRET', default='')

SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]
SOCIAL_AUTH_GOOGLE_OAUTH2_EXTRA_DATA = ['first_name', 'last_name']

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'ksiegowosc.auth_pipeline.assign_to_ksiegowosc_group',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

# KLUCZOWE: Poprawne ścieżki i przekierowania dla social-django
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/auth/dashboard/'
SOCIAL_AUTH_NEW_USER_REDIRECT_URL = '/admin/ksiegowosc/companyinfo/add/'
SOCIAL_AUTH_LOGIN_ERROR_URL = '/auth/login/'
SOCIAL_AUTH_URL_NAMESPACE = 'auth:social' # Naprawia redirect_uri_mismatch

# =============================================================================
# PASSWORD VALIDATION
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================
LANGUAGE_CODE = env('LANGUAGE_CODE', default='pl')
TIME_ZONE = env('TIME_ZONE', default='Europe/Warsaw')
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC FILES & MEDIA
# =============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = env('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = env('MEDIA_ROOT', default=str(BASE_DIR / 'media'))

# =============================================================================
# JAZZMIN, DEBUG TOOLBAR, ETC.
# =============================================================================

JAZZMIN_SETTINGS = {
    # Twoje ustawienia Jazzmin
    "site_title": "Fakturownia",
    "site_header": "Fakturownia",
    "site_brand": "Fakturownia",
    "welcome_sign": "Witaj w panelu Fakturowni",
    "copyright": "Fakturownia App",
    # ... reszta Twoich ustawień ...
}

if DEBUG:
    INTERNAL_IPS = ["127.0.0.1", "localhost"]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
