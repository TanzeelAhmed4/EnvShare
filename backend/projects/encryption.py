import base64
import binascii
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


ENCRYPTED_VALUE_PREFIX = 'aesgcm:v1:'
STANDARD_HISTORY_LEGACY_PREFIX = 'aesgcm:standard-history:v2:'
STANDARD_HISTORY_PREFIX = 'aesgcm:standard-history:v3:'
NONCE_LENGTH = 12
INVALID_KEY_MESSAGE = (
    'Sensitive value encryption key is invalid. Configure a Base64-encoded 32-byte key.'
)
HISTORY_KEY_NOT_CONFIGURED = (
    'Standard history encryption is not configured. Configure ENVSHARE_HISTORY_ENCRYPTION_KEY.'
)
INVALID_HISTORY_KEY_MESSAGE = (
    'Standard history encryption key is invalid. Configure a Base64-encoded 32-byte key.'
)
NON_DISTINCT_HISTORY_KEY_MESSAGE = (
    'Standard history encryption key must be separate from Django and Sensitive-value keys.'
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


def encryption_configuration_status():
    """Expose availability only; never return configuration material."""
    sensitive_available = True
    sensitive_reason = None
    try:
        _cipher()
    except EncryptionError as error:
        sensitive_available = False
        sensitive_reason = 'not_configured' if 'not configured' in str(error) else 'invalid_configuration'
    history_available = True
    history_reason = None
    try:
        _standard_history_cipher()
    except EncryptionError as error:
        history_available = False
        history_reason = 'not_configured' if 'not configured' in str(error) else 'invalid_configuration'
    return {
        'available': sensitive_available,
        'reason': sensitive_reason,
        'standard_history_available': history_available,
        'standard_history_reason': history_reason,
    }


def _associated_data(environment, key):
    return f'envshare:environment-variable:v1:{environment.pk}:{key}'.encode('utf-8')


def _encrypt_with_context(plaintext, associated_data):
    cipher = _cipher()
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = cipher.encrypt(nonce, plaintext.encode('utf-8'), associated_data)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')
    return f'{ENCRYPTED_VALUE_PREFIX}{payload}'


def _decrypt_with_context(envelope, associated_data):
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
        plaintext = cipher.decrypt(payload[:NONCE_LENGTH], payload[NONCE_LENGTH:], associated_data)
        return plaintext.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError, InvalidTag):
        raise EncryptionError('Sensitive value could not be decrypted.') from None


def historical_associated_data(version):
    context = [
        'envshare:variable-version:v1',
        version.project_id_snapshot,
        version.environment_id_snapshot,
        version.variable_id_snapshot,
        version.variable_key,
        version.version_number,
        version.sensitivity,
    ]
    return json.dumps(context, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


def _standard_history_cipher():
    encoded_key = getattr(settings, 'ENVSHARE_HISTORY_ENCRYPTION_KEY', '')
    if not encoded_key:
        raise EncryptionError(HISTORY_KEY_NOT_CONFIGURED)
    try:
        key = base64.b64decode(encoded_key.encode('ascii'), altchars=b'-_', validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise EncryptionError(INVALID_HISTORY_KEY_MESSAGE) from None
    if len(key) != 32:
        raise EncryptionError(INVALID_HISTORY_KEY_MESSAGE)
    if key == settings.SECRET_KEY.encode('utf-8'):
        raise EncryptionError(NON_DISTINCT_HISTORY_KEY_MESSAGE)
    sensitive_encoded_key = getattr(settings, 'ENVSHARE_ENCRYPTION_KEY', '')
    if sensitive_encoded_key:
        try:
            sensitive_key = base64.b64decode(
                sensitive_encoded_key.encode('ascii'), altchars=b'-_', validate=True,
            )
        except (UnicodeEncodeError, binascii.Error, ValueError):
            sensitive_key = None
        if sensitive_key is not None and key == sensitive_key:
            raise EncryptionError(NON_DISTINCT_HISTORY_KEY_MESSAGE)
    return AESGCM(key)


def _legacy_standard_history_key(secret_key=None):
    secret_key = settings.SECRET_KEY if secret_key is None else secret_key
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'envshare:history-key-derivation:v2',
        info=b'standard-variable-version-snapshots',
    ).derive(secret_key.encode('utf-8'))


def _legacy_standard_history_cipher(secret_key=None):
    """Read-only compatibility for v2 snapshots made with the Django key."""
    return AESGCM(_legacy_standard_history_key(secret_key))


def _encrypt_with_cipher(plaintext, associated_data, cipher, prefix):
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = cipher.encrypt(nonce, plaintext.encode('utf-8'), associated_data)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')
    return f'{prefix}{payload}'


def _decrypt_payload(cipher, payload, associated_data):
    decoded = base64.b64decode(payload.encode('ascii'), altchars=b'-_', validate=True)
    if len(decoded) < NONCE_LENGTH + 16:
        raise ValueError
    return cipher.decrypt(decoded[:NONCE_LENGTH], decoded[NONCE_LENGTH:], associated_data).decode('utf-8')


def encrypt_historical_value(plaintext, version_context):
    if version_context.sensitivity == 'standard':
        return _encrypt_with_cipher(
            plaintext, historical_associated_data(version_context),
            _standard_history_cipher(), STANDARD_HISTORY_PREFIX,
        )
    return _encrypt_with_context(plaintext, historical_associated_data(version_context))


def decrypt_historical_value(version):
    if version.sensitivity == 'standard' and version.encrypted_value.startswith(STANDARD_HISTORY_PREFIX):
        payload = version.encrypted_value[len(STANDARD_HISTORY_PREFIX):]
        try:
            return _decrypt_payload(_standard_history_cipher(), payload, historical_associated_data(version))
        except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError, InvalidTag):
            raise EncryptionError('Sensitive value could not be decrypted.') from None
    if version.sensitivity == 'standard' and version.encrypted_value.startswith(STANDARD_HISTORY_LEGACY_PREFIX):
        payload = version.encrypted_value[len(STANDARD_HISTORY_LEGACY_PREFIX):]
        context = historical_associated_data(version)
        try:
            return _decrypt_payload(_legacy_standard_history_cipher(), payload, context)
        except InvalidTag:
            # Allows an operator to preserve the legacy derived key in the
            # dedicated setting before rotating Django SECRET_KEY.
            try:
                return _decrypt_payload(_standard_history_cipher(), payload, context)
            except EncryptionError:
                raise
            except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError, InvalidTag):
                raise EncryptionError('Sensitive value could not be decrypted.') from None
        except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError):
            raise EncryptionError('Sensitive value could not be decrypted.') from None
    # Legacy snapshots used the sensitive-value key regardless of classification.
    return _decrypt_with_context(version.encrypted_value, historical_associated_data(version))


def encrypt_value(plaintext, environment, key):
    return _encrypt_with_context(plaintext, _associated_data(environment, key))


def decrypt_value(envelope, environment, key):
    return _decrypt_with_context(envelope, _associated_data(environment, key))
