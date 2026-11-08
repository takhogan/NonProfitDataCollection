"""Application-level encryption and lookup HMACs (DB-050, DB-051).

- ``encrypt`` / ``decrypt``: AES-256-GCM. Output is ``b"v1" + nonce(12) + ciphertext``.
  Used for phone numbers (``contact_endpoint.encrypted_address``), addresses,
  landmarks and free-text notes. The database only ever sees ciphertext.
- ``encrypt_text`` / ``decrypt_text``: the same, as URL-safe base64 text for
  values that live inside JSON columns (conversation state, report answers).
- ``lookup_hmac``: org-scoped HMAC-SHA256 so a phone number can be found again
  without storing it in clear or as a plain hash.

Keys come from ``DATA_ENCRYPTION_KEY`` and ``LOOKUP_HMAC_KEY`` (base64, 32 bytes),
mapped from Secret Manager in production. Local development derives clearly
non-secret keys so tests and demos run without setup; production refuses to
start without real keys (``Settings.validate_runtime``).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION = b"v1"
_DEV_KEY_LABEL = b"metron-local-dev-only"


def _key(raw: str, label: bytes) -> bytes:
    if raw:
        # Accept standard (openssl rand -base64) or URL-safe base64.
        norm = raw.strip().replace("-", "+").replace("_", "/")
        key = base64.b64decode(norm + "=" * (-len(norm) % 4))
        if len(key) != 32:
            raise ValueError("encryption keys must be 32 bytes (base64)")
        return key
    if get_settings().is_production:
        raise RuntimeError("encryption key missing in production")
    return hashlib.sha256(_DEV_KEY_LABEL + b"|" + label).digest()


def _data_key() -> bytes:
    return _key(get_settings().data_encryption_key, b"data")


def _hmac_key() -> bytes:
    return _key(get_settings().lookup_hmac_key, b"lookup")


def encrypt(plaintext: str) -> bytes:
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(_data_key()).encrypt(nonce, plaintext.encode("utf-8"), None)


def decrypt(blob: bytes) -> str:
    if not blob.startswith(_VERSION):
        raise ValueError("unknown ciphertext version")
    nonce, ct = blob[2:14], blob[14:]
    return AESGCM(_data_key()).decrypt(nonce, ct, None).decode("utf-8")


def encrypt_text(plaintext: str) -> str:
    return base64.urlsafe_b64encode(encrypt(plaintext)).decode("ascii")


def decrypt_text(token: str) -> str:
    return decrypt(base64.urlsafe_b64decode(token.encode("ascii")))


def lookup_hmac(org_id: str, channel: str, address: str) -> str:
    msg = f"{org_id}|{channel}|{address}".encode("utf-8")
    return hmac.new(_hmac_key(), msg, hashlib.sha256).hexdigest()
