"""
Zaawansowane middleware bezpieczeństwa dla aplikacji Fakturownia
Dodaj do MIDDLEWARE w settings.py jako jedne z pierwszych
"""

import re
import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.core.cache import cache
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.urls import reverse
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('django.security')

User = get_user_model()

class SecurityMiddleware(MiddlewareMixin):
    """
    Kompleksowe middleware bezpieczeństwa
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Konfiguracja
        self.max_requests_per_minute = getattr(settings, 'SECURITY_MAX_REQUESTS_PER_MINUTE', 60)
        self.max_failed_logins = getattr(settings, 'SECURITY_MAX_FAILED_LOGINS', 5)
        self.block_duration = getattr(settings, 'SECURITY_BLOCK_DURATION', 300)  # 5 minut
        self.suspicious_patterns = self._load_suspicious_patterns()
        self.blocked_ips = set()
        self.request_counts = defaultdict(list)
        
        super().__init__(get_response)
    
    def _load_suspicious_patterns(self) -> List[re.Pattern]:
        """Załaduj wzorce podejrzanych requestów"""
        patterns = [
            # SQL Injection attempts
            re.compile(r'(\bunion\b|\bselect\b|\binsert\b|\bdelete\b|\bdrop\b|\bcreate\b)', re.IGNORECASE),
            
            # XSS attempts
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            re.compile(r'javascript:', re.IGNORECASE),
            re.compile(r'on\w+\s*=', re.IGNORECASE),
            
            # Path traversal
            re.compile(r'\.\./', re.IGNORECASE),
            re.compile(r'\.\.\\', re.IGNORECASE),
            
            # Command injection
            re.compile(r'(\||\;|\&|\$\(|\`)', re.IGNORECASE),
            
            # File inclusion
            re.compile(r'(etc/passwd|boot\.ini|win\.ini)', re.IGNORECASE),
            
            # Common attack tools
            re.compile(r'(sqlmap|nmap|nikto|burp|metasploit)', re.IGNORECASE),
        ]
        return patterns
    
    def _get_client_ip(self, request) -> str:
        """Pobierz prawdziwy IP klienta"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        """Wygeneruj klucz cache"""
        return f"security:{prefix}:{hashlib.md5(identifier.encode()).hexdigest()}"
    
    def _is_whitelisted_ip(self, ip: str) -> bool:
        """Sprawdź czy IP jest na białej liście"""
        whitelist = getattr(settings, 'SECURITY_IP_WHITELIST', ['127.0.0.1', '::1'])
        return ip in whitelist
    
    def _check_rate_limiting(self, request) -> bool:
        """Sprawdź rate limiting per IP"""
        client_ip = self._get_client_ip(request)
        
        if self._is_whitelisted_ip(client_ip):
            return True
        
        cache_key = self._get_cache_key('rate_limit', client_ip)
        now = time.time()
        
        # Pobierz listę timestampów z cache
        timestamps = cache.get(cache_key, [])
        
        # Usuń stare timestampy (starsze niż 1 minuta)
        minute_ago = now - 60
        timestamps = [ts for ts in timestamps if ts > minute_ago]
        
        # Sprawdź czy przekroczono limit
        if len(timestamps) >= self.max_requests_per_minute:
            self._log_security_event(
                request, 
                'RATE_LIMIT_EXCEEDED', 
                f"IP: {client_ip}, Requests: {len(timestamps)}"
            )
            return False
        
        # Dodaj aktualny timestamp
        timestamps.append(now)
        cache.set(cache_key, timestamps, 60)
        
        return True
    
    def _check_suspicious_patterns(self, request) -> bool:
        """Sprawdź podejrzane wzorce w requestach"""
        # Sprawdź URL
        full_path = request.get_full_path()
        
        # Sprawdź query string i POST data
        data_to_check = [
            full_path,
            request.META.get('HTTP_USER_AGENT', ''),
            request.META.get('HTTP_REFERER', ''),
        ]
        
        # Dodaj POST data jeśli istnieje
        if hasattr(request, 'POST') and request.POST:
            data_to_check.extend(request.POST.values())
        
        # Sprawdź wzorce
        for pattern in self.suspicious_patterns:
            for data in data_to_check:
                if data and pattern.search(str(data)):
                    self._log_security_event(
                        request,
                        'SUSPICIOUS_PATTERN_DETECTED',
                        f"Pattern: {pattern.pattern}, Data: {data[:100]}"
                    )
                    return False
        
        return True
    
    def _check_blocked_ips(self, request) -> bool:
        """Sprawdź czy IP jest zablokowany"""
        client_ip = self._get_client_ip(request)
        
        if self._is_whitelisted_ip(client_ip):
            return True
        
        cache_key = self._get_cache_key('blocked_ip', client_ip)
        blocked_until = cache.get(cache_key)
        
        if blocked_until and time.time() < blocked_until:
            self._log_security_event(
                request,
                'BLOCKED_IP_ACCESS_ATTEMPT',
                f"IP: {client_ip}, Blocked until: {datetime.fromtimestamp(blocked_until)}"
            )
            return False
        
        return True
    
    def _block_ip(self, request, duration: int = None) -> None:
        """Zablokuj IP na określony czas"""
        client_ip = self._get_client_ip(request)
        
        if self._is_whitelisted_ip(client_ip):
            return
        
        duration = duration or self.block_duration
        block_until = time.time() + duration
        
        cache_key = self._get_cache_key('blocked_ip', client_ip)
        cache.set(cache_key, block_until, duration)
        
        self._log_security_event(
            request,
            'IP_BLOCKED',
            f"IP: {client_ip}, Duration: {duration}s, Until: {datetime.fromtimestamp(block_until)}"
        )
    
    def _check_user_agent(self, request) -> bool:
        """Sprawdź User-Agent pod kątem botów i ataków"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        
        # Lista znanych złośliwych botów
        bad_bots = [
            'sqlmap', 'nikto', 'nessus', 'openvas', 'w3af',
            'skipfish', 'libwww', 'webcollage', 'masscan',
            'zgrab', 'shodan', 'censys', 'binaryedge'
        ]
        
        for bot in bad_bots:
            if bot in user_agent:
                self._log_security_event(
                    request,
                    'MALICIOUS_BOT_DETECTED',
                    f"User-Agent: {user_agent[:200]}"
                )
                return False
        
        # Sprawdź czy User-Agent jest podejrzanie krótki lub długi
        if user_agent and (len(user_agent) < 10 or len(user_agent) > 500):
            self._log_security_event(
                request,
                'SUSPICIOUS_USER_AGENT',
                f"Length: {len(user_agent)}, User-Agent: {user_agent[:200]}"
            )
            return False
        
        return True
    
    def _check_request_method(self, request) -> bool:
        """Sprawdź metodę HTTP"""
        allowed_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
        
        if request.method not in allowed_methods:
            self._log_security_event(
                request,
                'INVALID_HTTP_METHOD',
                f"Method: {request.method}"
            )
            return False
        
        return True
    
    def _check_content_length(self, request) -> bool:
        """Sprawdź rozmiar requestu"""
        max_content_length = getattr(settings, 'SECURITY_MAX_CONTENT_LENGTH', 10 * 1024 * 1024)  # 10MB
        
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length and int(content_length) > max_content_length:
            self._log_security_event(
                request,
                'CONTENT_LENGTH_EXCEEDED',
                f"Content-Length: {content_length}, Max: {max_content_length}"
            )
            return False
        
        return True
    
    def _log_security_event(self, request, event_type: str, details: str = "") -> None:
        """Loguj zdarzenie bezpieczeństwa"""
        client_ip = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
        user = getattr(request, 'user', None)
        user_info = str(user) if user and user.is_authenticated else 'Anonymous'
        
        security_logger.warning(
            f"SECURITY_EVENT: {event_type} | "
            f"IP: {client_ip} | "
            f"User: {user_info} | "
            f"Path: {request.path} | "
            f"Method: {request.method} | "
            f"UA: {user_agent} | "
            f"Details: {details}"
        )
    
    def _create_security_response(self, request, reason: str) -> HttpResponse:
        """Utwórz odpowiedź bezpieczeństwa"""
        if request.path.startswith('/api/') or 'application/json' in request.META.get('HTTP_ACCEPT', ''):
            return JsonResponse({
                'error': 'Access denied',
                'code': 'SECURITY_VIOLATION'
            }, status=403)
        else:
            return HttpResponseForbidden(
                '<h1>Access Denied</h1>'
                '<p>Your request has been blocked for security reasons.</p>'
                '<p>If you believe this is an error, please contact the administrator.</p>'
            )
    
    def process_request(self, request):
        """Przetwórz przychodzący request"""
        
        # Sprawdź podstawowe zabezpieczenia
        if not self._check_request_method(request):
            return self._create_security_response(request, 'Invalid HTTP method')
        
        if not self._check_content_length(request):
            return self._create_security_response(request, 'Content too large')
        
        if not self._check_blocked_ips(request):
            return self._create_security_response(request, 'IP blocked')
        
        if not self._check_user_agent(request):
            self._block_ip(request, 3600)  # Zablokuj na 1 godzinę
            return self._create_security_response(request, 'Malicious bot detected')
        
        if not self._check_rate_limiting(request):
            self._block_ip(request, 900)  # Zablokuj na 15 minut
            return self._create_security_response(request, 'Rate limit exceeded')
        
        if not self._check_suspicious_patterns(request):
            self._block_ip(request, 1800)  # Zablokuj na 30 minut
            return self._create_security_response(request, 'Suspicious pattern detected')
        
        return None


class LoginSecurityMiddleware(MiddlewareMixin):
    """
    Middleware do ochrony endpointów logowania
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.max_attempts = getattr(settings, 'LOGIN_SECURITY_MAX_ATTEMPTS', 5)
        self.lockout_duration = getattr(settings, 'LOGIN_SECURITY_LOCKOUT_DURATION', 900)  # 15 minut
        super().__init__(get_response)
    
    def _get_client_ip(self, request) -> str:
        """Pobierz prawdziwy IP klienta"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def _is_login_request(self, request) -> bool:
        """Sprawdź czy to request logowania"""
        login_paths = [
            '/admin/login/',
            '/accounts/login/',
            '/api/auth/login/',
        ]
        
        return (request.method == 'POST' and 
                any(request.path.startswith(path) for path in login_paths))
    
    def _get_failed_attempts_key(self, ip: str, username: str = None) -> str:
        """Klucz dla nieudanych prób logowania"""
        if username:
            identifier = f"{ip}:{username}"
        else:
            identifier = ip
        return f"login_security:failed_attempts:{hashlib.md5(identifier.encode()).hexdigest()}"
    
    def _increment_failed_attempts(self, request, username: str = None) -> int:
        """Zwiększ licznik nieudanych prób"""
        client_ip = self._get_client_ip(request)
        cache_key = self._get_failed_attempts_key(client_ip, username)
        
        attempts = cache.get(cache_key, 0) + 1
        cache.set(cache_key, attempts, self.lockout_duration)
        
        security_logger.warning(
            f"FAILED_LOGIN_ATTEMPT: IP: {client_ip}, Username: {username}, "
            f"Attempts: {attempts}, Path: {request.path}"
        )
        
        return attempts
    
    def _reset_failed_attempts(self, request, username: str = None) -> None:
        """Zresetuj licznik nieudanych prób"""
        client_ip = self._get_client_ip(request)
        cache_key = self._get_failed_attempts_key(client_ip, username)
        cache.delete(cache_key)
    
    def _is_locked_out(self, request, username: str = None) -> bool:
        """Sprawdź czy użytkownik/IP jest zablokowany"""
        client_ip = self._get_client_ip(request)
        cache_key = self._get_failed_attempts_key(client_ip, username)
        
        attempts = cache.get(cache_key, 0)
        return attempts >= self.max_attempts
    
    def process_request(self, request):
        """Sprawdź blokadę logowania przed procesowaniem"""
        if not self._is_login_request(request):
            return None
        
        # Sprawdź blokadę per IP
        if self._is_locked_out(request):
            security_logger.warning(
                f"LOGIN_LOCKOUT: IP: {self._get_client_ip(request)}, "
                f"Path: {request.path}"
            )
            
            if request.path.startswith('/api/'):
                return JsonResponse({
                    'error': 'Too many failed login attempts. Please try again later.',
                    'code': 'LOGIN_LOCKOUT'
                }, status=429)
            else:
                return HttpResponseForbidden(
                    '<h1>Account Temporarily Locked</h1>'
                    '<p>Too many failed login attempts. Please try again later.</p>'
                )
        
        return None
    
    def process_response(self, request, response):
        """Sprawdź wynik logowania i aktualizuj liczniki"""
        if not self._is_login_request(request):
            return response
        
        username = None
        if hasattr(request, 'POST'):
            username = request.POST.get('username') or request.POST.get('email')
        
        # Jeśli logowanie się powiodło (przekierowanie lub 200)
        if response.status_code in [200, 302] and not any(
            error in response.content.decode('utf-8', errors='ignore').lower()
            for error in ['error', 'invalid', 'incorrect', 'failed']
        ):
            self._reset_failed_attempts(request, username)
            security_logger.info(
                f"SUCCESSFUL_LOGIN: IP: {self._get_client_ip(request)}, "
                f"Username: {username}, Path: {request.path}"
            )
        else:
            # Logowanie nieudane
            attempts = self._increment_failed_attempts(request, username)
            
            if attempts >= self.max_attempts:
                security_logger.critical(
                    f"LOGIN_LOCKOUT_TRIGGERED: IP: {self._get_client_ip(request)}, "
                    f"Username: {username}, Attempts: {attempts}"
                )
        
        return response


class AdminSecurityMiddleware(MiddlewareMixin):
    """
    Dodatkowe zabezpieczenia dla panelu admin
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_paths = ['/admin/', getattr(settings, 'ADMIN_URL', 'admin/')]
        super().__init__(get_response)
    
    def _is_admin_request(self, request) -> bool:
        """Sprawdź czy to request do panelu admin"""
        return any(request.path.startswith(path) for path in self.admin_paths)
    
    def _check_admin_ip_whitelist(self, request) -> bool:
        """Sprawdź whitelist IP dla admin"""
        admin_ip_whitelist = getattr(settings, 'ADMIN_IP_WHITELIST', None)
        
        if not admin_ip_whitelist:
            return True
        
        client_ip = self._get_client_ip(request)
        return client_ip in admin_ip_whitelist
    
    def _get_client_ip(self, request) -> str:
        """Pobierz prawdziwy IP klienta"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def process_request(self, request):
        """Sprawdź dostęp do panelu admin"""
        if not self._is_admin_request(request):
            return None
        
        # Sprawdź whitelist IP
        if not self._check_admin_ip_whitelist(request):
            security_logger.critical(
                f"ADMIN_ACCESS_DENIED: IP: {self._get_client_ip(request)} "
                f"not in whitelist, Path: {request.path}"
            )
            return HttpResponseForbidden(
                '<h1>Access Denied</h1>'
                '<p>Admin access is restricted to authorized IP addresses.</p>'
            )
        
        # Loguj dostęp do admin
        if request.user.is_authenticated:
            security_logger.info(
                f"ADMIN_ACCESS: User: {request.user}, "
                f"IP: {self._get_client_ip(request)}, Path: {request.path}"
            )
        
        return None


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """
    Middleware do ustawiania Content Security Policy
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp_policy = self._build_csp_policy()
        super().__init__(get_response)
    
    def _build_csp_policy(self) -> str:
        """Zbuduj politykę CSP"""
        policy_parts = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com",
            "font-src 'self' fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        
        # Dodaj dodatkowe dyrektywy z ustawień
        custom_csp = getattr(settings, 'CUSTOM_CSP_DIRECTIVES', {})
        for directive, values in custom_csp.items():
            if isinstance(values, list):
                values = ' '.join(values)
            policy_parts.append(f"{directive} {values}")
        
        return '; '.join(policy_parts)
    
    def process_response(self, request, response):
        """Dodaj nagłówek CSP"""
        if not getattr(settings, 'CSP_ENABLED', True):
            return response
        
        # Nie dodawaj CSP dla API responses JSON
        if response.get('Content-Type', '').startswith('application/json'):
            return response
        
        response['Content-Security-Policy'] = self.csp_policy
        return response
