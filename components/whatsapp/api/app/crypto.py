"""Application-level field encryption and lookup HMACs (DB-050, DB-051).

Envelope encryption with a Cloud KMS managed key:

- A random 32-byte **root key** is generated once and stored only wrapped
  (encrypted) by the KMS key ``KMS_KEY_NAME``. The wrapped value is the secret
  ``WRAPPED_DATA_KEY`` (base64). The plaintext root key never touches disk, the
  repo, an image or Secret Manager.
- At first use the process asks KMS to unwrap it (the runtime service account
  has only ``cloudkms.cryptoKeyDecrypter`` on that one key; every unwrap is in
  Cloud Audit Logs) and keeps the plaintext root key in memory only.
- From the root key, HKDF-SHA256 derives:
  - the **data key** (AES-256-GCM) for phone numbers, addresses, landmarks,
    points and free-text notes;
  - one **lookup HMAC key per organization** (DB-051), so one org's phone
    lookups and reporter keys cannot be matched against another's.

Rotation: rotating the KMS key only changes how the root key is wrapped
(re-wrap with ``gcloud kms decrypt | gcloud kms encrypt``); stored data stays
readable. Emergency wipe (hostile-state threat model): destroying the KMS key
versions makes every encrypted field unreadable, including in backups.

Local development and tests use a derived, clearly non-secret root key, so
nothing needs setting up. Production refuses to start without ``KMS_KEY_NAME``
and ``WRAPPED_DATA_KEY`` (``Settings.validate_runtime``).

Formats: ``encrypt`` returns ``b"v1" + nonce(12) + ciphertext``;
``encrypt_text`` returns that as URL-safe base64 for values inside JSON columns.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import threading

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

log = logging.getLogger("crypto")

_VERSION = b"v1"
_DEV_ROOT_LABEL = b"metron-local-dev-only-root"
_METADATA_TOKEN_URL = ("http://metadata.google.internal/computeMetadata/v1/instance/"
                       "service-accounts/default/token")
KMS_API = "https://cloudkms.googleapis.com/v1"

_lock = threading.Lock()
_root: bytes | None = None
_derived: dict[bytes, bytes] = {}


class KeyUnavailable(RuntimeError):
    """The root key could not be unwrapped (KMS down, no permission, bad config)."""


def _b64decode(raw: str) -> bytes:
    norm = raw.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(norm + "=" * (-len(norm) % 4))


def _access_token() -> str:
    """OAuth token of the runtime service account (Cloud Run metadata server)."""
    resp = httpx.get(_METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=5.0)
    resp.raise_for_status()
    return resp.json()["access_token"]


def unwrap_with_kms(key_name: str, wrapped: bytes) -> bytes:
    """Ask Cloud KMS to decrypt the wrapped root key. Retries transient errors."""
    last: Exception | None = None
    for _ in range(3):
        try:
            resp = httpx.post(
                f"{KMS_API}/{key_name}:decrypt",
                json={"ciphertext": base64.b64encode(wrapped).decode("ascii")},
                headers={"Authorization": f"Bearer {_access_token()}"},
                timeout=10.0,
            )
            if resp.status_code >= 500 or resp.status_code == 429:
                last = KeyUnavailable(f"KMS {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise KeyUnavailable(f"KMS decrypt refused: {resp.status_code}")
            return base64.b64decode(resp.json()["plaintext"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last = exc
    raise KeyUnavailable(f"KMS unwrap failed: {type(last).__name__}")


def _load_root() -> bytes:
    s = get_settings()
    if s.kms_key_name and s.wrapped_data_key:
        root = unwrap_with_kms(s.kms_key_name, _b64decode(s.wrapped_data_key))
        if len(root) != 32:
            raise KeyUnavailable("unwrapped root key must be 32 bytes")
        log.info("field-encryption root key unwrapped with Cloud KMS")
        return root
    if s.is_production:
        raise KeyUnavailable("KMS_KEY_NAME and WRAPPED_DATA_KEY are required in production")
    return hashlib.sha256(_DEV_ROOT_LABEL).digest()


def _root_key() -> bytes:
    global _root
    if _root is None:
        with _lock:
            if _root is None:
                _root = _load_root()
    return _root


def _derive(info: bytes) -> bytes:
    key = _derived.get(info)
    if key is None:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(_root_key())
        _derived[info] = key
    return key


def ensure_ready() -> None:
    """Unwrap the root key now (worker startup), so a KMS problem fails fast."""
    _root_key()


def reset_keys() -> None:
    """Forget cached keys (tests, or after re-wrapping)."""
    global _root
    with _lock:
        _root = None
        _derived.clear()


def _data_key() -> bytes:
    return _derive(b"metron|field-data|v1")


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
    """Org-scoped lookup HMAC (DB-051): each organization has its own derived key."""
    key = _derive(b"metron|lookup|v1|" + org_id.encode("utf-8"))
    return hmac.new(key, f"{channel}|{address}".encode("utf-8"), hashlib.sha256).hexdigest()
