# -*- coding: utf-8 -*-
"""BYOK key encryption. Users' provider API keys are stored encrypted at rest with
Fernet (AES); the plaintext key is only decrypted in-memory when a job needs it.

Dev: if FABULA_SECRET is unset, a key is generated and cached in data/.secret so
restarts stay consistent. Production: set FABULA_SECRET to a fixed Fernet key.
"""
import os, base64
from cryptography.fernet import Fernet
from .config import settings, ROOT

_SECRET_FILE = os.path.join(ROOT, "data", ".secret")


def _get_key():
    if settings.SECRET:
        return settings.SECRET.encode() if isinstance(settings.SECRET, str) else settings.SECRET
    os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
    if os.path.exists(_SECRET_FILE):
        return open(_SECRET_FILE, "rb").read().strip()
    key = Fernet.generate_key()
    with open(_SECRET_FILE, "wb") as f:
        f.write(key)
    return key


_fernet = Fernet(_get_key())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


def hint(plaintext: str) -> str:
    """A safe display hint, e.g. '••••••3f2a' — never the full key."""
    tail = plaintext[-4:] if len(plaintext) >= 4 else ""
    return "••••••" + tail
