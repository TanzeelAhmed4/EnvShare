from django.db import OperationalError, connection
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    if isinstance(exc, OperationalError):
        message = ' '.join(str(part) for part in getattr(exc, 'args', ())).lower()
        sqlite_lock = connection.vendor == 'sqlite' and any(
            marker in message for marker in ('database is locked', 'database table is locked', 'database is busy')
        )
        postgres_conflict = connection.vendor == 'postgresql' and any(
            marker in message for marker in ('deadlock detected', 'could not serialize access')
        )
        if sqlite_lock or postgres_conflict:
            return Response(
                {'detail': 'The request conflicted with another database write. Retry the operation.'},
                status=409,
            )
    return exception_handler(exc, context)
