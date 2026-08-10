import base64
import unittest
from cryptography.exceptions import InvalidTag
from cb_crypto import decrypt_message, encrypt_message, generate_chat_key, generate_identity, unwrap_chat_key, wrap_chat_key


class CryptoTest(unittest.TestCase):
    def test_member_envelopes(self):
        alice_private, alice_public = generate_identity()
        bob_private, bob_public = generate_identity()
        key = generate_chat_key()
        alice = wrap_chat_key(key, alice_public, "general", "alice")
        bob = wrap_chat_key(key, bob_public, "general", "bob")
        self.assertEqual(unwrap_chat_key(alice, alice_private, "general", "alice"), key)
        self.assertEqual(unwrap_chat_key(bob, bob_private, "general", "bob"), key)
        with self.assertRaises(InvalidTag):
            unwrap_chat_key(alice, bob_private, "general", "alice")

    def test_messages_are_context_bound_and_tamper_evident(self):
        key = generate_chat_key()
        nonce, ciphertext = encrypt_message("secret", key, "general", "alice")
        self.assertEqual(decrypt_message(nonce, ciphertext, key, "general", "alice"), "secret")
        with self.assertRaises(InvalidTag):
            decrypt_message(nonce, ciphertext, key, "other", "alice")
        raw = bytearray(base64.b64decode(ciphertext))
        raw[-1] ^= 1
        with self.assertRaises(InvalidTag):
            decrypt_message(nonce, base64.b64encode(raw).decode(), key, "general", "alice")


if __name__ == "__main__":
    unittest.main()

