"""
Encryption utilities for molt-md.
Uses AES-256-GCM for authenticated encryption.
"""

import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


def generate_key():
    """
    Generate a new 256-bit encryption key.
    Returns: Base64 URL-safe encoded key string.
    """
    raw_key = os.urandom(32)  # 256 bits
    key_b64 = base64.urlsafe_b64encode(raw_key).decode()
    return key_b64


def decode_key(key_b64):
    """
    Decode a Base64 URL-safe encoded key.
    Returns: Raw bytes key.
    """
    return base64.urlsafe_b64decode(key_b64)


def encrypt_content(content, raw_key):
    """
    Encrypt content using AES-256-GCM.

    Args:
        content: String content to encrypt
        raw_key: Raw bytes key (32 bytes)

    Returns:
        tuple: (ciphertext bytes, nonce bytes)
    """
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    aesgcm = AESGCM(raw_key)
    ciphertext = aesgcm.encrypt(nonce, content.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_content(ciphertext, nonce, raw_key):
    """
    Decrypt content using AES-256-GCM.

    Args:
        ciphertext: Encrypted bytes
        nonce: Nonce bytes used during encryption
        raw_key: Raw bytes key (32 bytes)

    Returns:
        String: Decrypted content

    Raises:
        InvalidTag: If decryption fails (wrong key or tampered data)
    """
    aesgcm = AESGCM(raw_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def verify_key(ciphertext, nonce, raw_key):
    """
    Verify that a key is correct by attempting decryption.

    Returns:
        bool: True if key is valid, False otherwise
    """
    try:
        decrypt_content(ciphertext, nonce, raw_key)
        return True
    except (InvalidTag, Exception):
        return False
