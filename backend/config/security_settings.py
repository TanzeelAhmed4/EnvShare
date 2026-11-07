import base64
import binascii
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


DEVELOPMENT_SECRET_KEY = 'envshare-local-development-only-change-me'


def _required(env, name):
    value = env.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'{name} must be configured when DJANGO_ENV=production.')
    return value


def production_settings(env):
    """Validate deployment-only configuration without ever including secrets in errors."""
    debug_value = env.get('DJANGO_DEBUG', 'false').strip().lower()
    if debug_value not in {'true', 'false', '1', '0'}:
        raise ImproperlyConfigured('DJANGO_DEBUG must be true or false.')
    if debug_value in {'true', '1'}:
        raise ImproperlyConfigured('DJANGO_DEBUG cannot be enabled when DJANGO_ENV=production.')
    secret_key = _required(env, 'DJANGO_SECRET_KEY')
    if secret_key == DEVELOPMENT_SECRET_KEY or len(secret_key) < 50:
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be a private value of at least 50 characters.')

    allowed_hosts = [host.strip() for host in _required(env, 'DJANGO_ALLOWED_HOSTS').split(',') if host.strip()]
    if not allowed_hosts or '*' in allowed_hosts or any('/' in host or '://' in host for host in allowed_hosts):
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must contain explicit host names.')

    cors_origins = [origin.strip() for origin in _required(env, 'DJANGO_CORS_ALLOWED_ORIGINS').split(',') if origin.strip()]
    if not cors_origins or any(
        urlsplit(origin).scheme != 'https'
        or not urlsplit(origin).netloc
        or urlsplit(origin).path
        or urlsplit(origin).query
        or urlsplit(origin).fragment
        for origin in cors_origins
    ):
        raise ImproperlyConfigured('DJANGO_CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins.')

    encoded_key = _required(env, 'ENVSHARE_ENCRYPTION_KEY')
    try:
        encryption_key = base64.b64decode(encoded_key.encode('ascii'), altchars=b'-_', validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ImproperlyConfigured('ENVSHARE_ENCRYPTION_KEY must be Base64 text for a 32-byte key.') from None
    if len(encryption_key) != 32:
        raise ImproperlyConfigured('ENVSHARE_ENCRYPTION_KEY must be Base64 text for a 32-byte key.')

    try:
        hsts_seconds = int(env.get('DJANGO_SECURE_HSTS_SECONDS', '86400'))
        session_age = int(env.get('DJANGO_SESSION_COOKIE_AGE', '3600'))
    except ValueError:
        raise ImproperlyConfigured('HSTS duration and session lifetime must be whole numbers.') from None
    if hsts_seconds < 86400:
        raise ImproperlyConfigured('DJANGO_SECURE_HSTS_SECONDS must be at least one day in production.')
    if not 300 <= session_age <= 31536000:
        raise ImproperlyConfigured('DJANGO_SESSION_COOKIE_AGE must be between 300 and 31536000 seconds.')
    include_subdomains = env.get('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'false').strip().lower() in {'true', '1'}
    preload = env.get('DJANGO_SECURE_HSTS_PRELOAD', 'false').strip().lower() in {'true', '1'}
    if preload and (not include_subdomains or hsts_seconds < 31536000):
        raise ImproperlyConfigured('HSTS preload requires subdomains and a one-year HSTS duration.')

    return {
        'SECRET_KEY': secret_key,
        'DEBUG': False,
        'ALLOWED_HOSTS': allowed_hosts,
        'CORS_ALLOWED_ORIGINS': cors_origins,
        'ENVSHARE_ENCRYPTION_KEY': encoded_key,
        'SECURE_HSTS_SECONDS': hsts_seconds,
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': include_subdomains,
        'SECURE_HSTS_PRELOAD': preload,
        'SESSION_COOKIE_AGE': session_age,
    }
