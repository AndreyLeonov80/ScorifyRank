from pathlib import Path

_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")


def where() -> str:
    return str(_CA_BUNDLE)


def contents() -> str:
    return _CA_BUNDLE.read_text(encoding="ascii")
