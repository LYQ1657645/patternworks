import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables


class CredentialsUnavailable(Exception):
    pass


def _cipher():
    return Fernet(settings.CONNECTION_ENCRYPTION_KEY.encode())


@sensitive_variables()
def encrypt_credentials(credentials):
    return _cipher().encrypt(json.dumps(credentials).encode())


@sensitive_variables()
def decrypt_credentials(connection):
    if connection.expires_at <= timezone.now() or not connection.encrypted_credentials:
        raise CredentialsUnavailable('Connection expired. Please reconnect.')
    try:
        return json.loads(_cipher().decrypt(bytes(connection.encrypted_credentials), ttl=settings.CONNECTION_TTL_SECONDS))
    except (InvalidToken, ValueError):
        raise CredentialsUnavailable('Connection expired or is unavailable. Please reconnect.') from None
