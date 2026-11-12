import base64
from types import SimpleNamespace

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.test import SimpleTestCase, override_settings

from .encryption import (
    EncryptionError, _encrypt_with_cipher, _legacy_standard_history_cipher,
    _legacy_standard_history_key, decrypt_historical_value, decrypt_value,
    encrypt_historical_value, encrypt_value, historical_associated_data,
)


VALID_TEST_KEY = base64.urlsafe_b64encode(b'K' * 32).decode('ascii')
VALID_HISTORY_TEST_KEY = base64.urlsafe_b64encode(b'H' * 32).decode('ascii')


def standard_version_context():
    return SimpleNamespace(
        sensitivity='standard', project_id_snapshot=1, environment_id_snapshot=2,
        variable_id_snapshot=3, variable_key='PUBLIC_VALUE', version_number=4,
    )


class EncryptionConfigurationTests(SimpleTestCase):
    @override_settings(ENVSHARE_ENCRYPTION_KEY=VALID_TEST_KEY)
    def test_valid_base64_32_byte_key_encrypts_and_decrypts(self):
        environment = SimpleNamespace(pk=123)
        encrypted = encrypt_value('test-plaintext', environment, 'TEST_KEY')

        self.assertTrue(encrypted.startswith('aesgcm:v1:'))
        self.assertNotIn('test-plaintext', encrypted)
        self.assertEqual(decrypt_value(encrypted, environment, 'TEST_KEY'), 'test-plaintext')

    @override_settings(ENVSHARE_ENCRYPTION_KEY='')
    def test_missing_key_has_missing_configuration_message(self):
        with self.assertRaises(EncryptionError) as raised:
            encrypt_value('test-plaintext', SimpleNamespace(pk=123), 'TEST_KEY')

        self.assertEqual(str(raised.exception), 'Sensitive value encryption is not configured.')
        self.assertNotIn('test-plaintext', str(raised.exception))

    @override_settings(ENVSHARE_ENCRYPTION_KEY='not-a-valid-base64-key')
    def test_malformed_key_is_reported_as_invalid_without_echoing_it(self):
        configured_key = 'not-a-valid-base64-key'
        with self.assertRaises(EncryptionError) as raised:
            encrypt_value('test-plaintext', SimpleNamespace(pk=123), 'TEST_KEY')

        self.assertIn('key is invalid', str(raised.exception))
        self.assertNotIn(configured_key, str(raised.exception))
        self.assertNotIn('test-plaintext', str(raised.exception))

    @override_settings(ENVSHARE_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'S' * 16).decode('ascii'))
    def test_base64_key_with_wrong_decoded_length_is_reported_as_invalid(self):
        with self.assertRaises(EncryptionError) as raised:
            encrypt_value('test-plaintext', SimpleNamespace(pk=123), 'TEST_KEY')

        self.assertIn('32-byte key', str(raised.exception))

    @override_settings(ENVSHARE_HISTORY_ENCRYPTION_KEY=VALID_HISTORY_TEST_KEY)
    def test_standard_history_uses_dedicated_key_and_survives_django_secret_change(self):
        version = standard_version_context()
        with self.settings(SECRET_KEY='first-django-secret'):
            encrypted = encrypt_historical_value('test-standard-history', version)
        self.assertTrue(encrypted.startswith('aesgcm:standard-history:v3:'))
        self.assertNotIn('test-standard-history', encrypted)
        version.encrypted_value = encrypted
        with self.settings(SECRET_KEY='different-django-secret'):
            self.assertEqual(decrypt_historical_value(version), 'test-standard-history')

    @override_settings(ENVSHARE_HISTORY_ENCRYPTION_KEY=VALID_HISTORY_TEST_KEY)
    def test_legacy_standard_history_formats_remain_readable(self):
        version = standard_version_context()
        context = historical_associated_data(version)
        version.encrypted_value = _encrypt_with_cipher(
            'legacy-sensitive-key-format', context,
            AESGCM(base64.urlsafe_b64decode(VALID_TEST_KEY)),
            'aesgcm:v1:',
        )
        with self.settings(ENVSHARE_ENCRYPTION_KEY=VALID_TEST_KEY):
            self.assertEqual(decrypt_historical_value(version), 'legacy-sensitive-key-format')

        with self.settings(SECRET_KEY='legacy-django-secret'):
            version.encrypted_value = _encrypt_with_cipher(
                'legacy-django-key-format', context,
                _legacy_standard_history_cipher(), 'aesgcm:standard-history:v2:',
            )
            legacy_derived_key = base64.urlsafe_b64encode(
                _legacy_standard_history_key('legacy-django-secret'),
            ).decode('ascii')
            self.assertEqual(decrypt_historical_value(version), 'legacy-django-key-format')
        with self.settings(SECRET_KEY='rotated-django-secret', ENVSHARE_HISTORY_ENCRYPTION_KEY=legacy_derived_key):
            self.assertEqual(decrypt_historical_value(version), 'legacy-django-key-format')

    @override_settings(ENVSHARE_HISTORY_ENCRYPTION_KEY='')
    def test_standard_history_missing_key_fails_with_safe_configuration_message(self):
        with self.assertRaises(EncryptionError) as raised:
            encrypt_historical_value('must-not-leak', standard_version_context())
        self.assertEqual(
            str(raised.exception),
            'Standard history encryption is not configured. Configure ENVSHARE_HISTORY_ENCRYPTION_KEY.',
        )
        self.assertNotIn('must-not-leak', str(raised.exception))

    @override_settings(ENVSHARE_HISTORY_ENCRYPTION_KEY='not-valid-history-key')
    def test_standard_history_invalid_key_fails_without_echoing_configuration(self):
        with self.assertRaises(EncryptionError) as raised:
            encrypt_historical_value('must-not-leak', standard_version_context())
        self.assertIn('key is invalid', str(raised.exception))
        self.assertNotIn('not-valid-history-key', str(raised.exception))
        self.assertNotIn('must-not-leak', str(raised.exception))

    @override_settings(
        ENVSHARE_ENCRYPTION_KEY=VALID_TEST_KEY,
        ENVSHARE_HISTORY_ENCRYPTION_KEY='',
    )
    def test_sensitive_value_encryption_does_not_depend_on_history_key(self):
        environment = SimpleNamespace(pk=123)
        encrypted = encrypt_value('sensitive-value', environment, 'PRIVATE')
        self.assertEqual(decrypt_value(encrypted, environment, 'PRIVATE'), 'sensitive-value')
        version = standard_version_context()
        version.sensitivity = 'sensitive'
        historical = encrypt_historical_value('sensitive-history', version)
        version.encrypted_value = historical
        self.assertTrue(historical.startswith('aesgcm:v1:'))
        self.assertEqual(decrypt_historical_value(version), 'sensitive-history')
