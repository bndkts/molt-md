"""
Encryption utilities for molt-md.
Uses AES-256-GCM for authenticated encryption.
"""

import os
import base64
import hashlib
import hmac
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
        raw_key: Raw bytes key (32 bytes) - should be the read key

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
        raw_key: Raw bytes key (32 bytes) - should be the read key

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


def derive_read_key(write_key_b64):
    """
    Derive a read key from a write key using HMAC-SHA256.
    
    Args:
        write_key_b64: Base64 URL-safe encoded write key
        
    Returns:
        String: Base64 URL-safe encoded read key
    """
    write_key_raw = decode_key(write_key_b64)
    # Use HMAC-SHA256 with the write key and a constant message
    read_key_raw = hmac.new(write_key_raw, b"molt-read", hashlib.sha256).digest()
    read_key_b64 = base64.urlsafe_b64encode(read_key_raw).decode()
    return read_key_b64


def hash_key(key_b64):
    """
    Generate SHA-256 hash of a key for storage/verification.
    
    Args:
        key_b64: Base64 URL-safe encoded key
        
    Returns:
        bytes: SHA-256 hash of the key
    """
    key_raw = decode_key(key_b64)
    return hashlib.sha256(key_raw).digest()
