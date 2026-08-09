import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from cb_server import ChatboisServer, User


class ServerResponseCodeTest(unittest.TestCase):
    def setUp(self):
        self.server = ChatboisServer(max_users=2, frequency=1)
        self.server.routes()
        self.client = TestClient(self.server.app)
        self.save = patch.object(self.server, "save_server").start()
        self.addCleanup(patch.stopall)

    def register(self, username):
        return self.client.post(f"/register/{username}")

    def test_registration_codes(self):
        self.assertEqual(self.register("alice").status_code, 201)
        self.assertEqual(self.register("alice").status_code, 409)
        self.assertEqual(self.register("bob").status_code, 201)
        self.assertEqual(self.register("charlie").status_code, 409)

        server = ChatboisServer(max_users=2, frequency=1)
        server.locked = True
        server.routes()
        self.assertEqual(TestClient(server.app).post("/register/alice").status_code, 423)

    def test_chat_creation_codes(self):
        self.server.users = {
            "alice": User(username="alice", uuid="alice-token"),
            "bob": User(username="bob", uuid="bob-token"),
        }
        url = "/make_chat/alice/general"
        self.assertEqual(self.client.post(url, json=["bob"]).status_code, 403)
        self.assertEqual(self.client.post(url, json=["alice", "missing"]).status_code, 404)
        self.assertEqual(self.client.post(url, json=["alice", "bob"]).status_code, 201)
        self.assertEqual(self.client.post(url, json=["alice", "bob"]).status_code, 409)

    def test_message_codes(self):
        self.server.users = {
            "alice": User(username="alice", uuid="alice-token"),
            "bob": User(username="bob", uuid="bob-token"),
        }
        self.client.post("/make_chat/alice/general", json=["alice"])
        missing = {"sender": "alice", "dest": "missing", "content": "hi"}
        forbidden = {"sender": "bob", "dest": "general", "content": "hi"}
        created = {"sender": "alice", "dest": "general", "content": "hi"}
        self.assertEqual(self.client.post("/send_message", json=missing).status_code, 404)
        self.assertEqual(self.client.post("/send_message", json=forbidden).status_code, 403)
        self.assertEqual(self.client.post("/send_message", json=created).status_code, 201)

    def test_completed_server_commands_return_ok(self):
        self.server.users["alice"] = User(username="alice", uuid="alice-token")
        self.assertEqual(self.client.post("/lock_server", params={"username": "alice"}).status_code, 200)
        response = self.client.post("/unlock_server", params={"username": "alice"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), "Server Unlocked")
        self.assertEqual(
            self.client.post(
                "/increment_users", params={"username": "alice", "increment": 1}
            ).status_code,
            200,
        )

    def test_chat_list_authentication_codes(self):
        self.server.users["alice"] = User(username="alice", uuid="alice-token")
        self.assertEqual(self.client.get("/get_chats/missing/token").status_code, 404)
        response = self.client.get("/get_chats/alice/wrong-token")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(self.client.get("/get_chats/alice/alice-token").status_code, 200)


if __name__ == "__main__":
    unittest.main()

