import asyncio
from enum import Enum
from pydantic import BaseModel, HttpUrl, WebsocketUrl
from rich.prompt import IntPrompt
from websockets import connect, ConnectionClosedError


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
    HttpURL: HttpUrl
    WebsocketUrl: WebsocketUrl


class ClientLayer(Enum):
    SERVER = 'server'
    CHAT = 'chat'
    MESSAGE = 'message'

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
        self.servers = servers
        self.layer = ClientLayer.SERVER

    async def connect(self, server: ClientServer):
        async with connect(
            f"{server.WebsocketUrl}?username={server.username}"
        ) as websocket:
            try:
                while True:
                    data = await websocket.recv()
            except ConnectionClosedError as e:
                print(f"Connection closed: {e}")

    async def run(self):
        tasks = [self.connect(server) for server in self.servers]
        await asyncio.gather(*tasks)

        """
    def select_server(self):
        servers_len = len(self.servers) + 1
        choices = {num: server.name for num, server in enumerate(self.servers, start=1)}
        choices[servers_len] = "Join New Server"
        for i, choice in choices.items():
            print(f'{i}) {choice}')
        selection = IntPrompt.ask('Which action do you want?', choices=choices, show_choices=True)

        print(f'{num+1}) Connect to New Server')
        """
