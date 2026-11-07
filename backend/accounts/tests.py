from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import get_hasher, identify_hasher
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.db import IntegrityError, transaction
from argon2.low_level import Type
from rest_framework.test import APIClient


class ProjectSetupTests(SimpleTestCase):
    def test_public_api_root_is_available(self):
        response = APIClient().get('/api/', HTTP_HOST='localhost')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'name': 'EnvShare API', 'status': 'ready'})

    def test_custom_user_model_is_preserved(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')
        self.assertEqual(get_user_model()._meta.label, 'accounts.User')

    def test_argon2_is_the_preferred_password_hasher(self):
        self.assertEqual(
            settings.PASSWORD_HASHERS[0],
            'django.contrib.auth.hashers.Argon2PasswordHasher',
        )
        self.assertEqual(get_hasher('argon2').params().type, Type.ID)

    def test_local_development_security_defaults_remain_usable(self):
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1209600)


class ProductionSettingsTests(SimpleTestCase):
    def valid_environment(self):
        import base64

        return {
            'DJANGO_ENV': 'production',
            'DJANGO_SECRET_KEY': 'test-only-secret-' + ('x' * 48),
            'DJANGO_ALLOWED_HOSTS': 'envshare.example.test,api.example.test',
            'DJANGO_CORS_ALLOWED_ORIGINS': 'https://envshare.example.test',
            'ENVSHARE_ENCRYPTION_KEY': base64.urlsafe_b64encode(b'P' * 32).decode('ascii'),
        }

    def test_production_configuration_requires_explicit_valid_settings(self):
        from config.security_settings import production_settings

        configured = production_settings(self.valid_environment())

        self.assertFalse(configured['DEBUG'])
        self.assertEqual(configured['ALLOWED_HOSTS'], ['envshare.example.test', 'api.example.test'])
        self.assertEqual(configured['SESSION_COOKIE_AGE'], 3600)
        self.assertEqual(configured['SECURE_HSTS_SECONDS'], 86400)

    def test_production_configuration_rejects_missing_or_invalid_encryption_key_safely(self):
        from django.core.exceptions import ImproperlyConfigured
        from config.security_settings import production_settings

        for value in ('', 'not-valid-base64', 'c2hvcnQ='):
            environment = self.valid_environment()
            environment['ENVSHARE_ENCRYPTION_KEY'] = value
            with self.subTest(key_configured=bool(value)):
                with self.assertRaises(ImproperlyConfigured) as raised:
                    production_settings(environment)
                if value:
                    self.assertNotIn(value, str(raised.exception))

    def test_production_configuration_rejects_debug_and_insecure_origins(self):
        from django.core.exceptions import ImproperlyConfigured
        from config.security_settings import production_settings

        environment = self.valid_environment()
        environment['DJANGO_DEBUG'] = 'true'
        with self.assertRaises(ImproperlyConfigured):
            production_settings(environment)
        environment = self.valid_environment()
        environment['DJANGO_CORS_ALLOWED_ORIGINS'] = 'http://envshare.example.test'
        with self.assertRaises(ImproperlyConfigured):
            production_settings(environment)


class AuthenticationApiTests(TestCase):
    valid_password = 'N3w-EnvShare!Passphrase-42'

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_post(self, path, data=None):
        csrf_response = self.client.get('/api/auth/csrf/', HTTP_HOST='localhost')
        self.assertEqual(csrf_response.status_code, 200)
        return self.client.post(
            path,
            data=data or {},
            format='json',
            HTTP_HOST='localhost',
            HTTP_X_CSRFTOKEN=csrf_response.json()['csrfToken'],
        )

    def register(self, username='envuser', email='envuser@example.com'):
        return self.csrf_post('/api/auth/register/', {
            'username': username,
            'email': email,
            'password': self.valid_password,
        })

    def test_registration_creates_argon2_user_and_starts_session(self):
        response = self.register()

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username='envuser')
        self.assertEqual(identify_hasher(user.password).algorithm, 'argon2')
        self.assertEqual(get_hasher('argon2').params().type, Type.ID)
        self.assertEqual(user.email, 'envuser@example.com')
        self.assertEqual(self.client.get('/api/auth/me/', HTTP_HOST='localhost').status_code, 200)

    def test_registration_rejects_duplicate_username_case_insensitively(self):
        self.register()

        response = self.register(username='ENVUSER', email='another@example.com')

        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.json())

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        self.register()

        response = self.register(username='another', email='ENVUSER@EXAMPLE.COM')

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())

    def test_database_constraints_reject_case_insensitive_username_and_email_duplicates(self):
        self.register()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    username='ENVUSER', email='another@example.com', password=self.valid_password,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    username='another', email='ENVUSER@EXAMPLE.COM', password=self.valid_password,
                )

    def test_registration_rejects_invalid_email_and_weak_password(self):
        invalid_email = self.csrf_post('/api/auth/register/', {
            'username': 'envuser', 'email': 'not-an-email', 'password': self.valid_password,
        })
        weak_password = self.csrf_post('/api/auth/register/', {
            'username': 'envuser', 'email': 'envuser@example.com', 'password': 'password',
        })

        self.assertEqual(invalid_email.status_code, 400)
        self.assertIn('email', invalid_email.json())
        self.assertEqual(weak_password.status_code, 400)
        self.assertIn('password', weak_password.json())

    def test_registration_rejects_missing_required_fields(self):
        response = self.csrf_post('/api/auth/register/', {'username': 'envuser'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.json())
        self.assertIn('password', response.json())

    def test_login_sets_session_and_invalid_credentials_are_rejected(self):
        user = get_user_model().objects.create_user(
            username='envuser', email='envuser@example.com', password=self.valid_password,
        )

        invalid = self.csrf_post('/api/auth/login/', {
            'username': user.username, 'password': 'wrong-password',
        })
        valid = self.csrf_post('/api/auth/login/', {
            'username': user.username, 'password': self.valid_password,
        })

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()['detail'], 'Username or password is incorrect.')
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()['username'], user.username)
        self.assertEqual(self.client.get('/api/auth/me/', HTTP_HOST='localhost').status_code, 200)

    def test_private_endpoint_rejects_anonymous_user(self):
        response = self.client.get('/api/auth/me/', HTTP_HOST='localhost')

        self.assertEqual(response.status_code, 403)

    def test_logout_clears_session(self):
        self.register()

        response = self.csrf_post('/api/auth/logout/')

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get('/api/auth/me/', HTTP_HOST='localhost').status_code, 403)

    def test_authentication_mutations_require_csrf(self):
        registration = self.client.post(
            '/api/auth/register/',
            {'username': 'envuser', 'email': 'envuser@example.com', 'password': self.valid_password},
            format='json',
            HTTP_HOST='localhost',
        )
        login_response = self.client.post(
            '/api/auth/login/',
            {'username': 'envuser', 'password': self.valid_password},
            format='json',
            HTTP_HOST='localhost',
        )
        user = get_user_model().objects.create_user(username='other', password=self.valid_password)
        self.client.force_login(user)
        logout_response = self.client.post(
            '/api/auth/logout/', format='json', HTTP_HOST='localhost',
        )

        self.assertEqual(registration.status_code, 403)
        self.assertEqual(login_response.status_code, 403)
        self.assertEqual(logout_response.status_code, 403)

    @override_settings(REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
        'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
        'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
        'DEFAULT_THROTTLE_RATES': {'login': '2/minute'},
    })
    def test_login_is_rate_limited_without_echoing_credentials(self):
        from unittest.mock import patch

        cache.clear()
        statuses = []
        with patch('accounts.auth_views.LoginAttemptThrottle.rate', '2/minute'):
            for _ in range(3):
                response = self.csrf_post('/api/auth/login/', {
                    'username': 'unknown-user', 'password': 'not-a-real-password',
                })
                statuses.append(response.status_code)
        self.assertEqual(statuses, [400, 400, 429])
        self.assertNotIn('not-a-real-password', response.content.decode())
        cache.clear()
