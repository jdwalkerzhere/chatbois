import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from cb_crypto import generate_identity
from cb_server import ChatboisServer


class EncryptedServerTest(unittest.TestCase):
    def setUp(self):
        self.server = ChatboisServer(max_users=3, frequency=1)
        self.server.routes()
        self.client = TestClient(self.server.app)
        patch.object(self.server, "save_server").start()
        self.addCleanup(patch.stopall)
        _, alice_public = generate_identity()
        _, bob_public = generate_identity()
        self.alice_token = self.register("alice", alice_public).json()["token"]
        self.bob_token = self.register("bob", bob_public).json()["token"]
        self.public_keys = {"alice": alice_public, "bob": bob_public}

    def register(self, name, public):
        return self.client.post(f"/register/{name}", json={"public_key": public})

    def test_keys_require_authentication(self):
        response = self.client.post(f"/public_keys/alice/{self.alice_token}", json=["alice", "bob"])
        self.assertEqual(response.json(), self.public_keys)
        self.assertEqual(self.client.post("/public_keys/alice/wrong", json=["alice"]).status_code, 401)
        self.assertEqual(self.register("bad", "plaintext").status_code, 422)

    def create_chat(self):
        return self.client.post("/make_chat/alice/general", params={"token": self.alice_token}, json={
            "users": ["alice", "bob"],
            "key_envelopes": {"alice": "YQ==", "bob": "Yg=="},
        })

    def test_envelopes_and_ciphertext_only_storage(self):
        self.assertEqual(self.create_chat().status_code, 201)
        message = {
            "sender": "alice", "dest": "general",
            "nonce": "MDEyMzQ1Njc4OWFi", "ciphertext": "bm90LXBsYWludGV4dA==",
        }
        self.assertEqual(self.client.post("/send_message", params={"token": "wrong"}, json=message).status_code, 401)
        self.assertEqual(self.client.post("/send_message", params={"token": self.alice_token}, json=message).status_code, 201)
        self.assertFalse(hasattr(self.server.chats["general"].history[0], "content"))
        alice = self.client.get(f"/get_chats/alice/{self.alice_token}").json()[0]
        bob = self.client.get(f"/get_chats/bob/{self.bob_token}").json()[0]
        self.assertEqual(alice["key_envelope"], "YQ==")
        self.assertEqual(bob["key_envelope"], "Yg==")
        self.assertNotIn("key_envelopes", alice)

    def test_chat_contract_rejects_bypass(self):
        body = {"users": ["alice"], "key_envelopes": {"alice": "YQ=="}}
        self.assertEqual(self.client.post("/make_chat/alice/bad", params={"token": "wrong"}, json=body).status_code, 401)
        missing = {"users": ["alice", "bob"], "key_envelopes": {"alice": "YQ=="}}
        self.assertEqual(self.client.post("/make_chat/alice/bad", params={"token": self.alice_token}, json=missing).status_code, 422)


if __name__ == "__main__":
    unittest.main()
