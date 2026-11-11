import os

from django.core.exceptions import ImproperlyConfigured


if os.environ.get('DJANGO_ENV', '').strip().lower() != 'production':
    raise ImproperlyConfigured('Production WSGI startup requires DJANGO_ENV=production.')

from .wsgi import application  # noqa: E402
