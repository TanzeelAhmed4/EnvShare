import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


ENCRYPTED_VALUE_PREFIX = 'aesgcm:v1:'
NONCE_LENGTH = 12
INVALID_KEY_MESSAGE = (
    'Sensitive value encryption key is invalid. Configure a Base64-encoded 32-byte key.'
)


class EncryptionError(Exception):
    """Safe-to-handle encryption failure; exception text never includes values or keys."""


def _cipher():
    encoded_key = getattr(settings, 'ENVSHARE_ENCRYPTION_KEY', '')
    if not encoded_key:
        raise EncryptionError('Sensitive value encryption is not configured.')
    try:
        key = base64.b64decode(encoded_key.encode('ascii'), altchars=b'-_', validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise EncryptionError(INVALID_KEY_MESSAGE) from None
    if len(key) != 32:
        raise EncryptionError(INVALID_KEY_MESSAGE)
    return AESGCM(key)


def _associated_data(environment, key):
    return f'envshare:environment-variable:v1:{environment.pk}:{key}'.encode('utf-8')


def encrypt_value(plaintext, environment, key):
    cipher = _cipher()
    iv = os.urandom(NONCE_LENGTH)
    ciphertext = cipher.encrypt(iv, plaintext.encode('utf-8'), _associated_data(environment, key))
    payload = base64.urlsafe_b64encode(iv + ciphertext).decode('ascii')
    return f'{ENCRYPTED_VALUE_PREFIX}{payload}'


def decrypt_value(envelope, environment, key):
    if not isinstance(envelope, str) or not envelope.startswith(ENCRYPTED_VALUE_PREFIX):
        raise EncryptionError('Sensitive value could not be decrypted.')
    cipher = _cipher()
    try:
        payload = base64.b64decode(
            envelope[len(ENCRYPTED_VALUE_PREFIX):].encode('ascii'),
            altchars=b'-_',
            validate=True,
        )
        if len(payload) < NONCE_LENGTH + 16:
            raise ValueError
        plaintext = cipher.decrypt(
            payload[:NONCE_LENGTH],
            payload[NONCE_LENGTH:],
            _associated_data(environment, key),
        )
        return plaintext.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError, InvalidTag):
        raise EncryptionError('Sensitive value could not be decrypted.') from None
