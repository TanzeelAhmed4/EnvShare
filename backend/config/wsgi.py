"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import sys

from django.core.wsgi import get_wsgi_application

if 'runserver' not in sys.argv and os.environ.get('DJANGO_ENV', '').strip().lower() != 'production':
    raise RuntimeError('WSGI startup requires DJANGO_ENV=production; use manage.py runserver for local development.')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
