import hashlib
import hmac
import math
import time
import unicodedata

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .serializers import CurrentUserSerializer, LoginSerializer, RegistrationSerializer


class LoginAttemptThrottle(SimpleRateThrottle):
    scope = 'login'
    rate = '5/minute'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


def _normalized_login_username(username):
    if not isinstance(username, str):
        return ''
    return unicodedata.normalize('NFKC', username).strip().lower()


def _login_username_cache_keys(username):
    normalized = _normalized_login_username(username)
    if not normalized:
        return None, None
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        normalized.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    prefix = f'envshare:login-user:v1:{digest}'
    return f'{prefix}:failures', f'{prefix}:cooldown'


def _login_username_cooldown_remaining(username):
    _, cooldown_key = _login_username_cache_keys(username)
    if cooldown_key is None:
        return 0
    cooldown_until = cache.get(cooldown_key)
    if cooldown_until is None:
        return 0
    return max(0, math.ceil(cooldown_until - time.time()))


def _record_login_username_failure(username):
    failure_key, cooldown_key = _login_username_cache_keys(username)
    if failure_key is None:
        return

    window = settings.LOGIN_USERNAME_FAILURE_WINDOW_SECONDS
    if cache.add(failure_key, 1, timeout=window):
        failures = 1
    else:
        try:
            failures = cache.incr(failure_key)
        except ValueError:
            if cache.add(failure_key, 1, timeout=window):
                failures = 1
            else:
                failures = cache.incr(failure_key)

    if failures >= settings.LOGIN_USERNAME_FAILURE_LIMIT:
        cooldown = settings.LOGIN_USERNAME_COOLDOWN_SECONDS
        cache.set(cooldown_key, time.time() + cooldown, timeout=cooldown)
        cache.delete(failure_key)


def _clear_login_username_failures(username):
    failure_key, cooldown_key = _login_username_cache_keys(username)
    if failure_key is not None:
        cache.delete_many((failure_key, cooldown_key))


class RegistrationAttemptThrottle(SimpleRateThrottle):
    scope = 'registration'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


def csrf_failure(request, reason=''):
    return JsonResponse(
        {'detail': 'CSRF verification failed. Refresh the page and try again.'},
        status=403,
    )


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'csrfToken': get_token(request._request)})


@method_decorator(csrf_protect, name='dispatch')
class RegistrationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationAttemptThrottle]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            return Response(
                {'detail': 'That username or email is already registered.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request._request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response(
            CurrentUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginAttemptThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        cooldown_remaining = _login_username_cooldown_remaining(username)
        if cooldown_remaining:
            raise Throttled(wait=cooldown_remaining)

        # Resolve the submitted spelling to the stored spelling before using
        # Django's exact username authentication lookup. Keep `username`
        # unchanged for failure tracking so casing variants share a bucket.
        matching_user = get_user_model().objects.filter(username__iexact=username).first()
        authentication_username = matching_user.get_username() if matching_user else username
        user = authenticate(
            request=request._request,
            username=authentication_username,
            password=serializer.validated_data['password'],
        )
        if user is None:
            _record_login_username_failure(username)
            return Response(
                {'detail': 'Username or password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _clear_login_username_failures(username)
        login(request._request, user)
        return Response(CurrentUserSerializer(user).data)


@method_decorator(csrf_protect, name='dispatch')
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
