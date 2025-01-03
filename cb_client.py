from enum import Enum
import os
from pydantic import BaseModel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich import print
import requests


def clear_terminal():
    command = "clr" if os.name == "nt" else "clear"
    os.system(command)


class Message(BaseModel):
    """
    Message class held in `Chat.history` field

    Fields:
        - sender (str): The user that sent the message to the server
        - dest (str): The name of the *Chat* that the message was sent to
        - content(str): The actual message content
    """

    sender: str
    dest: str
    content: str


class Chat(BaseModel):
    """
    Chat class held in `ChatboisServer.chats` field

    Fields:
        - name (str): The name the server recognizes the chat by
        - users (set[str]): The users that are able to access this chat instance
        - history (list[Message]): The message history of that chat among its users (No implicit copying of default list thanks to Pydantic BaseModel)
    """

    name: str
    users: list[str]
    history: list[Message] = []


class ClientServer(BaseModel):
    """
    ClientServer is used to populate the ClientConfig class.

    This class's fields are populated either by reading from the `client_config.json` or from a call to `build_client_config`.

    Fields:
        - username: the name that the ChatboisServer recognizes the user by
        - HttpURL: the HTTP URL that the ChatboisServer you're connecting to is running at
        - WebsocketUrl: The Websocket URL that the ChatboisServer the user is connectiging to is running at
    """

    name: str
    username: str
    uuid: str | None
    HttpURL: str


class ClientLayer(Enum):
    SERVER = "server"
    CHAT = "chat"
    MESSAGE = "message"


class ChatboisClient:
    """
    The *thin* ChatboisClient that provides a viewport into the ChatboisServer that holds all state.

    The user-loop of the ChatboisClient is effectively:
        - Connect to servers
        - Run Client
            - Choose Server
                - Choose Chat
                    - Send / Receive Messages
                - Make Chat
                    - Select Users
                        - Confirm Users
                    - Choose Chat

    At any point in time the user will have several choices in action:
    - Up and Down Navigation between choices
        - Server Choices:
            - Known Servers
            - Connect to New Server
        - Chat Choices:
            - Known Chats
            - Make New Chat
        - User Choices:
            - Known Users
            - Find User
        - Message Choices:
            - Up and Down Navigation in Chat history
            - New Message
        - Out (TAB)
            - Out functions in the following ways:
                - If in a Chat -> Out to Chat Selection
                - If in a Chat Selection -> Out to Server Selection
    """

    def __init__(self, servers: list[ClientServer]):
        self.servers: dict[str, ClientServer] = {
            server.name: server for server in servers
        }
        self.layer = ClientLayer.SERVER
        self.chats: dict[str, Chat] | None = None

    def nav_levels(self):
        match self.layer:
            case ClientLayer.SERVER:
                self.nav_server()
            case ClientLayer.CHAT:
                self.nav_chat()
            case ClientLayer.MESSAGE:
                self.nav_message()

    def nav_server(self):
        clear_terminal()
        server = self.select_server()
        if server == "Join New Server":
            server = self.register_new_server()
        assert not isinstance(server, str)
        self.current_server = server
        self.layer = ClientLayer.CHAT
        return

    def select_server(self) -> ClientServer | str:
        choices = {
            i: server_name for i, server_name in enumerate(self.servers.keys(), start=1)
        }
        choices.update({len(choices) + 1: "Join New Server"})
        for i, choice in choices.items():
            print(f"[bold green]{i})[/bold green] {choice}")
        selection = choices[IntPrompt.ask("[bold italic]Which server do you want?")]
        if selection not in self.servers:
            return selection
        return self.servers[selection]

    def register_new_server(self) -> ClientServer:
        add_server = Confirm.ask("Add new server?")
        if not add_server:
            known_server = list(self.servers.values())[0]
            print(f"Connecting to known server: {known_server.name}")
            return known_server
        name = Prompt.ask("What do you want to call this server?")
        server_http_address = Prompt.ask("What address is the server running at? (include whether http or https)")
        server_http_address = f'{server_http_address}'
        registered = Confirm.ask("Have you Registered with this Server Yet?")
        uuid = None
        if registered:
            username = Prompt.ask("What is your username for this server?")
        else:
            while True:
                username = Prompt.ask(
                    "What do you want your username to be for this Server?"
                )
                sucessful_register = requests.post(f"{server_http_address}/register/{username}")
                if sucessful_register.status_code == 202:
                    uuid = sucessful_register.json()["token"]
                    break

        new_server = ClientServer(
            name=name, username=username, uuid=uuid, HttpURL=server_http_address
        )
        self.servers.update({new_server.name: new_server})
        return new_server

    def nav_chat(self):
        clear_terminal()
        self.chats = (
            self.get_chats()
        )  # Request Chat History from Server / Store as field
        selection = self.select_chat()
        match selection:
            case "Make new Chat":
                self.make_chat()
                return
            case "Navigate Servers":
                self.layer = ClientLayer.SERVER
                return
            case _:
                self.current_chat = self.chats[selection]
                self.layer = ClientLayer.MESSAGE
                return

    def select_chat(self) -> str:
        assert self.chats is not None
        choices = {
            i: chat_name for i, chat_name in enumerate(self.chats.keys(), start=1)
        }
        choices.update({len(choices) + 1: "Make new Chat"})
        choices.update({len(choices) + 1: "Navigate Servers"})
        for i, choice in choices.items():
            print(f"[bold green]{i})[/bold green] {choice}")
        selection = choices[IntPrompt.ask("[bold italic]Which action do you want?")]
        return selection

    def make_chat(self):
        clear_terminal()
        while True:
            url = f"{self.current_server.HttpURL}/make_chat/"
            chatname = Prompt.ask("[bold italic]What do you want to call this Chat?")
            username = self.current_server.username
            members = []
            while True:
                add_member = Confirm.ask(
                    f"[bold]Add member to [italic]{chatname}[/italic] Chat?"
                )
                if not add_member:
                    break
                # TODO: Make this more user friendly, handle non-existing users
                members.append(Prompt.ask(f"[bold italic]Who do you want to add?"))
            response = requests.post(f"{url}{username}/{chatname}", json=members)
            if response.status_code == 202:
                break
            print(f"Error creating chat {chatname}: {response.json()}")

        return

    def get_chats(self) -> dict[str, Chat]:
        url = f"{self.current_server.HttpURL}/get_chats/"
        query = f"{self.current_server.username}/{self.current_server.uuid}"
        chats = requests.get(f"{url}{query}").json()

        if chats == f"User {self.current_server.username} has no chats to fetch":
            return {}

        return {chat["name"]: Chat(**chat) for chat in chats}

    def nav_message(self):
        clear_terminal()
        self.current_chat = self.get_chats()[self.current_chat.name]
        for message in self.current_chat.history:
            if message.sender == self.current_server.username:
                print(f"[bold dim]{message.sender}[/bold dim]: {message.content}")
            else:
                print(f"[bold blue]{message.sender}[/bold blue]: {message.content}")

        choices = {"1": "Send Message", "2": "Update", "3": "Nav Out to Chats"}
        for i, choice in choices.items():
            print(f"[bold red]{i}) {choice}")
        choice = Prompt.ask("[bold italic]Which Action", choices=["1", "2", "3"])
        match choices[choice]:
            case "Nav Out to Chats":
                self.layer = ClientLayer.CHAT
                return
            case "Update":
                self.current_chat = self.get_chats()[self.current_chat.name]
                return
            case "Send Message":
                self.send_message(Prompt.ask("Your Message"))
                return

    def send_message(self, content: str):
        message = Message(
            sender=self.current_server.username,
            dest=self.current_chat.name,
            content=content,
        )

        requests.post(
            f"{self.current_server.HttpURL}/send_message", json=message.model_dump()
        )
        self.current_chat = self.get_chats()[self.current_chat.name]

    def run(self):
        clear_terminal()
        while True:
            self.nav_levels()
