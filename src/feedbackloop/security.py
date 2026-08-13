from __future__ import annotations

from pathlib import Path, PurePosixPath


_SENSITIVE_NAMES = {
    ".aws",
    ".dockerconfigjson",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
_SENSITIVE_SUFFIXES = (".jks", ".key", ".keystore", ".p12", ".pem", ".pfx")


def is_sensitive_path(path: str | Path) -> bool:
    normalized = PurePosixPath(str(path).replace("\\", "/"))
    for part in normalized.parts:
        lowered = part.casefold()
        if (
            lowered == ".git"
            or lowered == ".env"
            or lowered.startswith(".env.")
            or lowered in _SENSITIVE_NAMES
            or lowered.endswith(_SENSITIVE_SUFFIXES)
        ):
            return True
    return False
