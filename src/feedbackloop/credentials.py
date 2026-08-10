from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from pydantic import Field

from feedbackloop.models import DomainModel


class KeyringProtocol(Protocol):
    def get(self, provider: str) -> str | None: ...
    def set(self, provider: str, key: str) -> None: ...
    def delete(self, provider: str) -> None: ...


class CredentialStatus(DomainModel):
    provider: str
    configured: bool
    fingerprint: str | None = Field(default=None, repr=False)


class SystemKeyring:
    SERVICE = "feedbackloop-harness"

    def get(self, provider: str) -> str | None:
        import keyring

        return keyring.get_password(self.SERVICE, provider)

    def set(self, provider: str, key: str) -> None:
        import keyring

        keyring.set_password(self.SERVICE, provider, key)

    def delete(self, provider: str) -> None:
        import keyring

        try:
            keyring.delete_password(self.SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass


class _BoundCredentialProvider:
    def __init__(self, keyring: KeyringProtocol, provider: str) -> None:
        self._keyring = keyring
        self._provider = provider

    def get(self, provider: str) -> str | None:
        if provider != self._provider:
            return None
        return self._keyring.get(self._provider)


class CredentialService:
    def __init__(self, keyring: KeyringProtocol | None = None) -> None:
        self._keyring = keyring or SystemKeyring()

    def set(self, provider: str, key: str) -> None:
        if not provider.strip() or not key:
            raise ValueError("provider and key are required")
        self._keyring.set(provider, key)

    def status(self, provider: str) -> CredentialStatus:
        key = self._keyring.get(provider)
        fingerprint = sha256(key.encode("utf-8")).hexdigest()[:12] if key else None
        return CredentialStatus(
            provider=provider,
            configured=key is not None,
            fingerprint=fingerprint,
        )

    def clear(self, provider: str) -> None:
        self._keyring.delete(provider)

    def build_provider(self, provider: str) -> _BoundCredentialProvider:
        return _BoundCredentialProvider(self._keyring, provider)
