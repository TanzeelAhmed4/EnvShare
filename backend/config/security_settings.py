import base64
import binascii
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


DEVELOPMENT_SECRET_KEY = 'envshare-local-development-only-change-me'
PRODUCTION_SECRET_PLACEHOLDER = 'REPLACE_WITH_PRIVATE_RANDOM_VALUE_AT_LEAST_50_CHARACTERS'


def _is_placeholder_secret(value):
    normalized = value.strip().casefold()
    known_fallbacks = {
        DEVELOPMENT_SECRET_KEY.casefold(),
        PRODUCTION_SECRET_PLACEHOLDER.casefold(),
        'django-insecure-change-this-in-production',
        'changeme',
        'change-me',
        'your-secret-key',
        'your-django-secret-key',
    }
    return (
        normalized in known_fallbacks
        or normalized.startswith(('replace_with_', 'replace-me', 'changeme-', 'your-secret'))
        or normalized.startswith('django-insecure-')
    )


def _required(env, name):
    value = env.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'{name} must be configured when DJANGO_ENV=production.')
    return value


def _boolean(env, name, default='false'):
    value = env.get(name, default).strip().lower()
    if value not in {'true', 'false', '1', '0'}:
        raise ImproperlyConfigured(f'{name} must be true or false.')
    return value in {'true', '1'}


def production_settings(env):
    """Validate deployment-only configuration without ever including secrets in errors."""
    if _boolean(env, 'DJANGO_DEBUG'):
        raise ImproperlyConfigured('DJANGO_DEBUG cannot be enabled when DJANGO_ENV=production.')
    secret_key = _required(env, 'DJANGO_SECRET_KEY')
    if len(secret_key) < 50 or _is_placeholder_secret(secret_key):
        raise ImproperlyConfigured('DJANGO_SECRET_KEY must be a private value of at least 50 characters.')

    allowed_hosts = [host.strip() for host in _required(env, 'DJANGO_ALLOWED_HOSTS').split(',') if host.strip()]
    if not allowed_hosts or any('*' in host or '/' in host or '://' in host or any(ch.isspace() for ch in host) for host in allowed_hosts):
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must contain explicit host names.')

    cors_origins = [origin.strip() for origin in _required(env, 'DJANGO_CORS_ALLOWED_ORIGINS').split(',') if origin.strip()]
    try:
        parsed_origins = [urlsplit(origin) for origin in cors_origins]
        invalid_origin = not cors_origins or any(
            parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or parsed.port == 0
            for parsed in parsed_origins
        )
    except ValueError:
        invalid_origin = True
    if invalid_origin:
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
    include_subdomains = _boolean(env, 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS')
    preload = _boolean(env, 'DJANGO_SECURE_HSTS_PRELOAD')
    if preload and (not include_subdomains or hsts_seconds < 31536000):
        raise ImproperlyConfigured('HSTS preload requires subdomains and a one-year HSTS duration.')

    cache_url = _required(env, 'ENVSHARE_CACHE_URL')
    cache_parts = urlsplit(cache_url)
    if cache_parts.scheme not in {'redis', 'rediss'} or not cache_parts.hostname:
        raise ImproperlyConfigured('ENVSHARE_CACHE_URL must be a Redis or TLS Redis URL.')

    trust_proxy = _boolean(env, 'DJANGO_TRUST_PROXY_SSL_HEADER')

    log_level = env.get('ENVSHARE_LOG_LEVEL', 'INFO').strip().upper()
    if log_level not in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
        raise ImproperlyConfigured('ENVSHARE_LOG_LEVEL is invalid.')

    email_enabled = env.get('ENVSHARE_EMAIL_ENABLED', 'false').strip().lower()
    if email_enabled not in {'true', 'false', '1', '0'}:
        raise ImproperlyConfigured('ENVSHARE_EMAIL_ENABLED must be true or false.')
    email_enabled = email_enabled in {'true', '1'}
    email = {}
    if email_enabled:
        email_host = _required(env, 'EMAIL_HOST')
        email_from = _required(env, 'DEFAULT_FROM_EMAIL')
        try:
            email_port = int(env.get('EMAIL_PORT', '587'))
        except ValueError:
            raise ImproperlyConfigured('EMAIL_PORT must be a valid port.') from None
        if not 1 <= email_port <= 65535:
            raise ImproperlyConfigured('EMAIL_PORT must be a valid port.')
        use_tls = _boolean(env, 'EMAIL_USE_TLS', 'true')
        use_ssl = _boolean(env, 'EMAIL_USE_SSL')
        if use_tls and use_ssl:
            raise ImproperlyConfigured('EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.')
        email_user = env.get('EMAIL_HOST_USER', '')
        email_password = env.get('EMAIL_HOST_PASSWORD', '')
        if bool(email_user) != bool(email_password):
            raise ImproperlyConfigured('EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be configured together.')
        email = {
            'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'EMAIL_HOST': email_host,
            'EMAIL_PORT': email_port,
            'EMAIL_HOST_USER': email_user,
            'EMAIL_HOST_PASSWORD': email_password,
            'EMAIL_USE_TLS': use_tls,
            'EMAIL_USE_SSL': use_ssl,
            'DEFAULT_FROM_EMAIL': email_from,
        }

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
        'CACHE_URL': cache_url,
        'TRUST_PROXY_SSL_HEADER': trust_proxy,
        'LOG_LEVEL': log_level,
        'EMAIL_ENABLED': email_enabled,
        **email,
    }
