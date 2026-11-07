import base64
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from .encryption import EncryptionError, decrypt_value, encrypt_value


VALID_TEST_KEY = base64.urlsafe_b64encode(b'K' * 32).decode('ascii')


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
