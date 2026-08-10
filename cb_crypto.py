import base64
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def generate_identity() -> tuple[str, str]:
    private = X25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _encode(private_bytes), _encode(public_bytes)


def generate_chat_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def _wrapping_key(shared_secret: bytes, chat_name: str, recipient: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"chatbois:key:v1:{chat_name}:{recipient}".encode(),
    ).derive(shared_secret)


def wrap_chat_key(chat_key: bytes, recipient_public_key: str, chat_name: str, recipient: str) -> str:
    ephemeral = X25519PrivateKey.generate()
    public = X25519PublicKey.from_public_bytes(_decode(recipient_public_key))
    wrapping_key = _wrapping_key(ephemeral.exchange(public), chat_name, recipient)
    nonce = os.urandom(12)
    aad = f"chatbois:key-envelope:v1:{chat_name}:{recipient}".encode()
    ciphertext = AESGCM(wrapping_key).encrypt(nonce, chat_key, aad)
    ephemeral_public = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _encode(ephemeral_public + nonce + ciphertext)


def unwrap_chat_key(envelope: str, private_key: str, chat_name: str, recipient: str) -> bytes:
    payload = _decode(envelope)
    if len(payload) < 61:
        raise ValueError("Invalid chat-key envelope")
    ephemeral_public = X25519PublicKey.from_public_bytes(payload[:32])
    private = X25519PrivateKey.from_private_bytes(_decode(private_key))
    wrapping_key = _wrapping_key(private.exchange(ephemeral_public), chat_name, recipient)
    aad = f"chatbois:key-envelope:v1:{chat_name}:{recipient}".encode()
    return AESGCM(wrapping_key).decrypt(payload[32:44], payload[44:], aad)


def encrypt_message(plaintext: str, chat_key: bytes, chat_name: str, sender: str) -> tuple[str, str]:
    nonce = os.urandom(12)
    aad = f"chatbois:message:v1:{chat_name}:{sender}".encode()
    ciphertext = AESGCM(chat_key).encrypt(nonce, plaintext.encode(), aad)
    return _encode(nonce), _encode(ciphertext)


def decrypt_message(nonce: str, ciphertext: str, chat_key: bytes, chat_name: str, sender: str) -> str:
    aad = f"chatbois:message:v1:{chat_name}:{sender}".encode()
    plaintext = AESGCM(chat_key).decrypt(_decode(nonce), _decode(ciphertext), aad)
    return plaintext.decode()

