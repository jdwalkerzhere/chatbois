import os
from enum import Enum
import requests
from pydantic import BaseModel, Field
from rich import print
from rich.prompt import Confirm, IntPrompt, Prompt
from cb_crypto import decrypt_message, encrypt_message, generate_chat_key, generate_identity, unwrap_chat_key, wrap_chat_key
from cb_db import save


class EncryptedMessage(BaseModel):
    sender: str
    dest: str
    nonce: str
    ciphertext: str


class Chat(BaseModel):
    name: str
    users: list[str]
    key_envelope: str
    history: list[EncryptedMessage] = Field(default_factory=list)


class ClientServer(BaseModel):
    name: str
    username: str
    uuid: str
    HttpURL: str
    private_key: str
    public_key: str


class ClientLayer(Enum):
    SERVER = "server"
    CHAT = "chat"
    MESSAGE = "message"


def clear_terminal():
    os.system("clr" if os.name == "nt" else "clear")


class ChatboisClient:
    """Endpoint that keeps identity/chat keys and plaintext local."""

    def __init__(self, servers: list[ClientServer]):
        self.servers = {server.name: server for server in servers}
        self.layer = ClientLayer.SERVER
        self.chats = {}

    def save(self):
        save("client_config", {"servers": [server.model_dump(mode="json") for server in self.servers.values()]})

    def register_new_server(self):
        name = Prompt.ask("What do you want to call this server?")
        address = Prompt.ask("Server address (include http or https)")
        username = Prompt.ask("What username do you want?")
        private_key, public_key = generate_identity()
        response = requests.post(f"{address}/register/{username}", json={"public_key": public_key})
        response.raise_for_status()
        server = ClientServer(name=name, username=username, uuid=response.json()["token"], HttpURL=address, private_key=private_key, public_key=public_key)
        self.servers[name] = server
        self.save()
        return server

    def nav_server(self):
        clear_terminal()
        choices = {i: name for i, name in enumerate(self.servers, 1)}
        choices[len(choices) + 1] = "Join New Server"
        for number, choice in choices.items():
            print(f"[bold green]{number})[/bold green] {choice}")
        selected = choices[IntPrompt.ask("Which server?")]
        self.current_server = self.register_new_server() if selected == "Join New Server" else self.servers[selected]
        self.layer = ClientLayer.CHAT

    def get_chats(self):
        response = requests.get(f"{self.current_server.HttpURL}/get_chats/{self.current_server.username}/{self.current_server.uuid}")
        response.raise_for_status()
        return {item["name"]: Chat(**item) for item in response.json()}

    def make_chat(self):
        name = Prompt.ask("Chat name")
        members = [self.current_server.username]
        while Confirm.ask(f"Add member to {name}?"):
            member = Prompt.ask("Username")
            if member not in members:
                members.append(member)
        auth = f"{self.current_server.username}/{self.current_server.uuid}"
        response = requests.post(f"{self.current_server.HttpURL}/public_keys/{auth}", json=members)
        response.raise_for_status()
        key = generate_chat_key()
        envelopes = {user: wrap_chat_key(key, public, name, user) for user, public in response.json().items()}
        response = requests.post(f"{self.current_server.HttpURL}/make_chat/{self.current_server.username}/{name}", params={"token": self.current_server.uuid}, json={"users": members, "key_envelopes": envelopes})
        response.raise_for_status()

    def nav_chat(self):
        clear_terminal()
        self.chats = self.get_chats()
        choices = {i: name for i, name in enumerate(self.chats, 1)}
        choices[len(choices) + 1] = "Make new Chat"
        choices[len(choices) + 1] = "Navigate Servers"
        for number, choice in choices.items():
            print(f"[bold green]{number})[/bold green] {choice}")
        selected = choices[IntPrompt.ask("Which action?")]
        if selected == "Make new Chat":
            self.make_chat()
        elif selected == "Navigate Servers":
            self.layer = ClientLayer.SERVER
        else:
            self.current_chat = self.chats[selected]
            self.layer = ClientLayer.MESSAGE

    def chat_key(self, chat):
        return unwrap_chat_key(chat.key_envelope, self.current_server.private_key, chat.name, self.current_server.username)

    def nav_message(self):
        clear_terminal()
        self.current_chat = self.get_chats()[self.current_chat.name]
        key = self.chat_key(self.current_chat)
        for message in self.current_chat.history:
            try:
                content = decrypt_message(message.nonce, message.ciphertext, key, message.dest, message.sender)
            except Exception:
                content = "[unable to decrypt or message was tampered with]"
            print(f"{message.sender}: {content}")
        choice = Prompt.ask("1) Send 2) Update 3) Chats", choices=["1", "2", "3"])
        if choice == "1":
            self.send_message(Prompt.ask("Your Message"))
        elif choice == "3":
            self.layer = ClientLayer.CHAT

    def send_message(self, content):
        nonce, ciphertext = encrypt_message(content, self.chat_key(self.current_chat), self.current_chat.name, self.current_server.username)
        message = EncryptedMessage(sender=self.current_server.username, dest=self.current_chat.name, nonce=nonce, ciphertext=ciphertext)
        response = requests.post(f"{self.current_server.HttpURL}/send_message", params={"token": self.current_server.uuid}, json=message.model_dump())
        response.raise_for_status()

    def run(self):
        while True:
            {ClientLayer.SERVER: self.nav_server, ClientLayer.CHAT: self.nav_chat, ClientLayer.MESSAGE: self.nav_message}[self.layer]()

