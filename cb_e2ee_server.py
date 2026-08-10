import base64
from typing import Annotated
from uuid import uuid4
import uvicorn
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from cb_db import load, save


class Registration(BaseModel):
    public_key: str


class User(BaseModel):
    username: str
    uuid: str
    public_key: str
    chats: list[str] = Field(default_factory=list)


class EncryptedMessage(BaseModel):
    sender: str
    dest: str
    nonce: str
    ciphertext: str


class ChatCreate(BaseModel):
    users: list[str]
    key_envelopes: dict[str, str]


class Chat(BaseModel):
    name: str
    users: list[str]
    key_envelopes: dict[str, str]
    history: list[EncryptedMessage] = Field(default_factory=list)


def valid_b64(value: str, length: int | None = None) -> bool:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return False
    return length is None or len(raw) == length


class ChatboisServer:
    """Authenticated relay that persists only E2EE envelopes and ciphertext."""

    def __init__(self, max_users: int, frequency: int):
        self.max_users, self.frequency = max_users, frequency
        self.app, self.users, self.chats = FastAPI(), {}, {}
        self.locked = False

    def run(self):
        try:
            self.users = {key: User(**value) for key, value in load("users", {}).items()}
            self.chats = {key: Chat(**value) for key, value in load("chats", {}).items()}
        except Exception as error:
            raise RuntimeError("Legacy plaintext state cannot be loaded; start with a new database.") from error
        self.routes()
        uvicorn.run(self.app, host="0.0.0.0", port=5000)

    def save_server(self):
        save("users", {key: value.model_dump(mode="json") for key, value in self.users.items()})
        save("chats", {key: value.model_dump(mode="json") for key, value in self.chats.items()})

    def authenticated(self, username: str, token: str) -> bool:
        return username in self.users and self.users[username].uuid == token

    def routes(self):
        @self.app.post("/register/{username}")
        async def register(username: str, registration: Registration):
            if len(self.users) >= self.max_users:
                return JSONResponse(status_code=409, content="Server at User Capacity")
            if self.locked:
                return JSONResponse(status_code=423, content="Server is Locked")
            if username in self.users:
                return JSONResponse(status_code=409, content="Username already exists")
            if not valid_b64(registration.public_key, 32):
                return JSONResponse(status_code=422, content="Invalid X25519 public key")
            user = User(username=username, uuid=str(uuid4()), public_key=registration.public_key)
            self.users[username] = user
            self.save_server()
            return JSONResponse(status_code=201, content={"username": username, "token": user.uuid})

        @self.app.post("/public_keys/{username}/{token}")
        async def public_keys(username: str, token: str, users: list[str]):
            if not self.authenticated(username, token):
                return JSONResponse(status_code=401, content="Invalid credentials")
            if any(user not in self.users for user in users):
                return JSONResponse(status_code=404, content="Unknown user")
            return {user: self.users[user].public_key for user in users}

        @self.app.post("/make_chat/{username}/{chatname}")
        async def make_chat(username: str, chatname: str, token: str, request: ChatCreate):
            if not self.authenticated(username, token):
                return JSONResponse(status_code=401, content="Invalid credentials")
            if username not in request.users:
                return JSONResponse(status_code=403, content="Creator must be a member")
            if chatname in self.chats:
                return JSONResponse(status_code=409, content="Chat already exists")
            if any(user not in self.users for user in request.users):
                return JSONResponse(status_code=404, content="Unknown user")
            if set(request.users) != set(request.key_envelopes):
                return JSONResponse(status_code=422, content="Each member requires one key envelope")
            if any(not valid_b64(value) for value in request.key_envelopes.values()):
                return JSONResponse(status_code=422, content="Invalid key envelope")
            self.chats[chatname] = Chat(name=chatname, users=request.users, key_envelopes=request.key_envelopes)
            for user in request.users:
                self.users[user].chats.append(chatname)
            self.save_server()
            return JSONResponse(status_code=201, content="Encrypted chat created")

        @self.app.post("/send_message")
        async def send_message(message: Annotated[EncryptedMessage, Body()], token: str):
            if not self.authenticated(message.sender, token):
                return JSONResponse(status_code=401, content="Invalid credentials")
            if message.dest not in self.chats:
                return JSONResponse(status_code=404, content="Chat not found")
            if message.sender not in self.chats[message.dest].users:
                return JSONResponse(status_code=403, content="Sender is not a member")
            if not valid_b64(message.nonce, 12) or not valid_b64(message.ciphertext):
                return JSONResponse(status_code=422, content="Invalid encrypted message")
            self.chats[message.dest].history.append(message)
            self.save_server()
            return JSONResponse(status_code=201, content="Encrypted message delivered")

        @self.app.get("/get_chats/{username}/{token}")
        async def get_chats(username: str, token: str):
            if username not in self.users:
                return JSONResponse(status_code=404, content="Username not found")
            if not self.authenticated(username, token):
                return JSONResponse(status_code=401, content="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
            result = []
            for name in self.users[username].chats:
                chat = self.chats[name]
                item = chat.model_dump(exclude={"key_envelopes"})
                item["key_envelope"] = chat.key_envelopes[username]
                result.append(item)
            return result

