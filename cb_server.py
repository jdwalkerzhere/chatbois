from __future__ import annotations
import json
import logging
from typing import Annotated, Optional
from fastapi import Body, FastAPI, Request, status
from fastapi.responses import JSONResponse
from os import listdir
from pydantic import BaseModel
from rich import print
from uuid import uuid4
import uvicorn


class User(BaseModel):
    """
    User class held in the `ChatboisServer.users` field

    Fields:
        - username (str): The name the server recognizes the user by
        - uuid (UUID4): [Currently Unneccessary] Useful down the line if users want to replace their username
        - chats (list[str]): List of the chatnames the user is a part of (useful for get_chats method)
    """

    username: str
    uuid: str
    chats: Optional[list[str]] = None


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


class ChatboisServer:
    """
    The ChatboisServer is the *heavy* source-of-truth server for the chatbois program.

    The Server holds all of the state for users, chats, messages, etc. The ChatboisClient in comparison is a viewport into the server.

    The Server exposes a number of simple API's for adding users, chats, and messages, and controlling server-wide state (like locking).

    The Server also exposes a websocket connection for the client to get immediate message updates from chats they are a part of.

    Fields:
        - max_users (int): The number beyond which no new users can register (w/out another user being deleted)
        - frequency (int): In increments of 15 seconds, how frequently the server should autosave state
        - app (FastAPI): The FastAPI that powers this whole d@mn thing
        - users (dict[str, User]): The users that have been registered to the server
        - active_users (dict[str, WebSocket]): Active websocket connections (username protected)
        - chats (dict[str, Chat]): The chats that have been created in the server
        - logger (Logger): Utility to console out info or warnings to the command line
        - locked (bool): Whether the server is locked from receiveing new user registration or not (username protected)
    """

    def __init__(self, max_users: int, frequency: int):
        self.max_users = max_users
        self.app = FastAPI()
        self.users: dict[str, User] = {}
        self.chats: dict[str, Chat] = {}
        self.logger = logging.getLogger(name="uvicorn")
        self.locked = False

    def run(self):
        """
        Exectution and hosting of the server. First Registers all routes and then runs via `uvicorn`
        """
        if "chats.json" in listdir():
            with open("chats.json", "r") as chats_file:
                print("[bold green]Reading Chats from saved server")
                chats = json.load(chats_file)
                self.chats = {
                    chatname: Chat(**chatdata) for chatname, chatdata in chats.items()
                    }

        if "users.json" in listdir():
            with open("users.json", "r") as user_file:
                print("[bold green]Reading Users from saved server")
                users = json.load(user_file)
                self.users = {
                    username: User(**userdata) for username, userdata in users.items()
                    }

        self.routes()
        uvicorn.run(self.app, host="0.0.0.0", port=5000)

    def save_server(self):
        print("[bold green italic]SAVING SERVER")
        with open("users.json", "w") as user_file:
            json.dump(
                {username: user.model_dump(mode='json') for username, user in self.users.items()},
                user_file,
                indent=4,
            )

        with open("chats.json", "w") as chats_file:
            json.dump(
                {chatname: chat.model_dump(mode='json') for chatname, chat in self.chats.items()},
                chats_file,
                indent=4,
            )

    def routes(self):
        """
        All ChatboisServer Routes are defined in the routes function (including the websocket)
        """

        @self.app.get("/info")
        async def info(request: Request) -> JSONResponse:
            """
            Non-username protected info method to provide the HTTP and Websocket URLs for the Server.

            Fails:
                - If max_users already reached
                - If server is locked
            """
            if len(self.users) >= self.max_users or self.locked:
                return JSONResponse(
                    status_code=status.HTTP_423_LOCKED,
                    content="Server at User Capacity",
                )

            assert request is not None and request.client is not None
            host = request.client.host
            server_port = request.scope.get("server")[1]
            response = {
                "http_url": f"http://{host}:{server_port}",
            }
            return JSONResponse(status_code=status.HTTP_200_OK, content=response)

        @self.app.post("/register/{username}")
        async def register(username: str) -> JSONResponse:
            """
            Registers a new user into the server

            Arguments:
                - username (str): The username the request is asking to register

            Fails:
                - If username already used
                - If max_users already reached
                - If server is locked
            """
            self.logger.info(f"Attempting to Register User [{username}]")
            if len(self.users) == self.max_users or self.locked:
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content="Server at User Capacity",
                )

            if username in self.users:
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content=f"Username [{username}] Already Exists",
                )

            new_user = User(username=username, uuid=str(uuid4()))
            self.logger.info(f"New User {username} created with token {new_user.uuid}")
            self.users[username] = new_user
            response = {"username": username, "token": new_user.uuid}
            self.save_server()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=response,
            )

        @self.app.post("/make_chat/{username}/{chatname}")
        async def make_chat(
            chatname: str, username: str, users: list[str]
        ) -> JSONResponse:
            """
            Creates a chat in the server for the given users

            Fails:
                - If username not present in chat
                - If chatname already exists
                - If any user in users is unrecognized by server
            """
            if username not in users:
                self.logger.info(f"Username {username} not found")
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content="Cannot create chat for other users",
                )

            if chatname in self.chats:
                self.logger.info(f"Chatname {chatname} already exists")
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content=f"Chat [{chatname}] Already Exists",
                )

            invalid_users = [user for user in users if user not in self.users]
            if invalid_users:
                self.logger.info(f"Some invalid users: {invalid_users}")
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content=f"Users [{invalid_users}] Not Present in Server, Cannot be Added to Chat",
                )

            new_chat = Chat(name=chatname, users=users)
            self.chats[chatname] = new_chat

            for user in new_chat.users:
                if not self.users[user].chats:
                    self.users[user].chats = []
                self.users[user].chats.append(new_chat.name)
            self.save_server()
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=f"New Chat [{chatname}] added with users {users}",
            )

        @self.app.post("/send_message")
        async def send_message(message: Annotated[Message, Body()]) -> JSONResponse:
            """
            Accepts Message, writes it to its chat, and notifies active_users in that chat

            Fails:
                - if message.dest (Chat.name) not recognized by server
                - if message.sender not present in message.dest (Chat.users)
            """
            sender, destination = message.sender, message.dest

            if destination not in self.chats:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=f"Chat [{destination}] Not Present in Server",
                )

            if sender not in self.chats[destination].users:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=f"User [{sender}] Not Authorized to Message Chat [{destination}]",
                )

            self.chats[destination].history.append(message)
            self.save_server()
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=f"Message from {sender} Delivered to Chat [{destination}]",
            )

        @self.app.post("/lock_server")
        async def lock_server(username: str) -> JSONResponse:
            """
            Locks the server such that no new members can join
            """
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content=f"Non-member User Cannot Lock Server",
                )

            self.locked = True
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED, content="Server Locked"
            )

        @self.app.post("/unlock_server")
        async def unlock_server(username: str) -> JSONResponse:
            """
            Unlocks the server such that new members can join
            """
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content="Non-member User cannot Unlock Server",
                )

            self.locked = False
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED, content="Server Now Locked"
            )

        @self.app.post("/increment_users")
        async def increment_server(username: str, increment: int) -> JSONResponse:
            """
            Increases `ChatboisServer.max_users` by `increment`
            """
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content="Non-member User cannot Increment Server Max Users",
                )

            self.max_users += increment
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=f"Server Max Users Increased to {self.max_users}",
            )

        @self.app.get("/get_chats/{username}/{token}")
        async def get_chats(username: str, token: str) -> JSONResponse:
            """
            Sends a user (confirmed by their token) their chats
            """
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content="Username not found in Server",
                )

            if self.users[username].uuid != token:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content="Token does not match username",
                )

            if not self.users[username].chats:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=f"User {username} has no chats to fetch",
                )

            json_chats = [self.chats[chat].model_dump() for chat in self.users[username].chats]
            return JSONResponse(status_code=status.HTTP_200_OK, content=json_chats)
