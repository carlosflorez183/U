"""Generación y verificación de credenciales sin almacenar secretos en claro."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedCredential:
    api_key: str
    secret_key: str
    api_key_digest: str
    api_key_prefix: str
    secret_salt: bytes
    secret_hash: bytes


class CredentialHasher:
    """Usa HMAC para localizar API keys y scrypt para verificar secrets."""

    _SCRYPT_N = 2**14
    _SCRYPT_R = 8
    _SCRYPT_P = 1
    _SCRYPT_LENGTH = 32
    _SCRYPT_MAX_MEMORY = 64 * 1024 * 1024

    def __init__(self, pepper: str) -> None:
        self._pepper = pepper.encode("utf-8")
        self._dummy_salt = secrets.token_bytes(16)
        self._dummy_hash = self._hash_secret("invalid-secret", self._dummy_salt)

    def generate(self) -> GeneratedCredential:
        api_key = "ak_" + secrets.token_urlsafe(24)
        secret_key = "sk_" + secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        return GeneratedCredential(
            api_key=api_key,
            secret_key=secret_key,
            api_key_digest=self.digest_api_key(api_key),
            api_key_prefix=api_key[:12],
            secret_salt=salt,
            secret_hash=self._hash_secret(secret_key, salt),
        )

    def digest_api_key(self, api_key: str) -> str:
        return hmac.new(
            self._pepper,
            api_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_secret(self, secret_key: str, salt: bytes, expected: bytes) -> bool:
        calculated = self._hash_secret(secret_key, salt)
        return hmac.compare_digest(calculated, expected)

    def consume_dummy_verification(self, secret_key: str) -> None:
        self.verify_secret(secret_key, self._dummy_salt, self._dummy_hash)

    @classmethod
    def _hash_secret(cls, secret_key: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            secret_key.encode("utf-8"),
            salt=salt,
            n=cls._SCRYPT_N,
            r=cls._SCRYPT_R,
            p=cls._SCRYPT_P,
            dklen=cls._SCRYPT_LENGTH,
            maxmem=cls._SCRYPT_MAX_MEMORY,
        )


class AdminAuthenticator:
    """Verifica en tiempo constante las credenciales bootstrap administrativas."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key = api_key
        self._secret_key = secret_key

    def verify(self, api_key: str, secret_key: str) -> bool:
        return hmac.compare_digest(api_key, self._api_key) and hmac.compare_digest(
            secret_key,
            self._secret_key,
        )