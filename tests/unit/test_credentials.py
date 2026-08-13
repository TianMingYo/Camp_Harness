from feedbackloop.credentials import CredentialService


class MemoryKeyring:
    def __init__(self):
        self.values = {}

    def get(self, provider: str):
        return self.values.get(provider)

    def set(self, provider: str, key: str):
        self.values[provider] = key

    def delete(self, provider: str):
        self.values.pop(provider, None)


def test_credential_status_never_returns_secret():
    keyring = MemoryKeyring()
    service = CredentialService(keyring)
    service.set("demo", "secret-value")
    status = service.status("demo")
    assert status.configured is True
    assert "secret-value" not in repr(status)
    assert "secret-value" not in status.model_dump_json()


def test_credential_update_and_clear():
    keyring = MemoryKeyring()
    service = CredentialService(keyring)
    service.set("demo", "first")
    service.set("demo", "second")
    provider = service.build_provider("demo")
    assert provider.get("demo") == "second"

    service.clear("demo")
    assert service.status("demo").configured is False
    assert provider.get("demo") is None


def test_provider_wrapper_does_not_expose_other_provider():
    keyring = MemoryKeyring()
    service = CredentialService(keyring)
    service.set("demo", "value")
    assert service.build_provider("demo").get("other") is None
