import secrets

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def live(request):
    return JsonResponse({'status': 'ok'})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            if cursor.fetchone()[0] != 1:
                raise RuntimeError('database probe failed')
        key = f'envshare:health:{secrets.token_hex(16)}'
        marker = secrets.token_hex(16)
        cache.set(key, marker, timeout=5)
        healthy = cache.get(key) == marker
        cache.delete(key)
        if not healthy:
            raise RuntimeError('cache probe failed')
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ready'})
