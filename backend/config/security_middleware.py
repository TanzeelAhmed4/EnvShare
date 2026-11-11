import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


_SENSITIVE_ASSIGNMENT = re.compile(
    r'''(?i)(["']?[A-Z0-9_]*(?:password|passwd|authorization|cookie|sessionid|csrfmiddlewaretoken|'''
    r'''access[_-]?token|refresh[_-]?token|invitation[_-]?token|token|secret(?:[_-]?key)?|'''
    r'''private[_-]?key|encryption[_-]?key|api[_-]?key|credential)'''
    r'''["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\r\n,;&}]+)'''
)
_AUTHORIZATION = re.compile(r'''(?i)(["']?authorization["']?\s*[:=]\s*)(?:Bearer\s+)?[^\r\n]+''')
_BEARER = re.compile(r'(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*')


def _redact(value):
    if not isinstance(value, str):
        return value
    value = _AUTHORIZATION.sub(r'\1[REDACTED]', value)
    value = _SENSITIVE_ASSIGNMENT.sub(r'\1[REDACTED]', value)
    return _BEARER.sub(r'\1[REDACTED]', value)


class SensitiveDataFilter(logging.Filter):
    """Scrub common credential-shaped values from formatted log messages."""

    def filter(self, record):
        record.msg = _redact(record.getMessage())
        record.args = ()
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)
        return True


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            event['exception'] = _redact(self.formatException(record.exc_info))
        return json.dumps(event, ensure_ascii=True, separators=(',', ':'))


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Content-Security-Policy', settings.CSP_POLICY)
        return response


class AdminLoginRateLimitMiddleware:
    """Apply a small IP-based cache limit to Django admin password attempts."""

    limit = 20
    window_seconds = 300
    cooldown_seconds = 60
    path = '/admin/login/'

    def __init__(self, get_response):
        self.get_response = get_response

    def _keys(self, request):
        address = request.META.get('REMOTE_ADDR', '')
        digest = hmac.new(
            settings.SECRET_KEY.encode('utf-8'), address.encode('utf-8'), hashlib.sha256,
        ).hexdigest()
        prefix = f'envshare:admin-login:v1:{digest}'
        return f'{prefix}:failures', f'{prefix}:cooldown'

    def __call__(self, request):
        if request.path_info == self.path and request.method == 'POST':
            _, cooldown_key = self._keys(request)
            try:
                until = cache.get(cooldown_key)
            except Exception:
                return HttpResponse('Authentication is temporarily unavailable.', status=503)
            if until and until > time.time():
                return HttpResponse('Too many login attempts. Try again shortly.', status=429)

        response = self.get_response(request)
        if request.path_info == self.path and request.method == 'POST':
            failure_key, cooldown_key = self._keys(request)
            try:
                if response.status_code == 200:
                    if cache.add(failure_key, 1, timeout=self.window_seconds):
                        failures = 1
                    else:
                        try:
                            failures = cache.incr(failure_key)
                        except ValueError:
                            failures = 1 if cache.add(failure_key, 1, timeout=self.window_seconds) else cache.incr(failure_key)
                    if failures >= self.limit:
                        cache.set(cooldown_key, time.time() + self.cooldown_seconds, timeout=self.cooldown_seconds)
                        cache.delete(failure_key)
                elif 300 <= response.status_code < 400:
                    cache.delete_many((failure_key, cooldown_key))
            except Exception:
                return HttpResponse('Authentication is temporarily unavailable.', status=503)
        return response
