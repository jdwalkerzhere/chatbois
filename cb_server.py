from __future__ import annotations
import logging
from typing import Annotated
from fastapi import Body, FastAPI, Request, WebSocket, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, BaseModel
from uuid import uuid4
import uvicorn


class User(BaseModel):
    """
    User class held in the `ChatboisServer.users` field

    Fields:
        - username (str): The name the server recognizes the user by
        - uuid (UUID4): [Currently Unneccessary] Useful down the line if users want to replace their username
    """
    username: str
    uuid: UUID4


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
    users: set[str]
    history: list[Message] = []


class ChatboisServer:
    """
    The ChatboisServer is the *heavy* source-of-truth server for the chatbois program.

    The Server holds all of the state for users, chats, messages, etc. The ChatboisClient in comparison is a viewport into the server.

    The Server exposes a number of simple API's for adding users, chats, and messages, and controlling server-wide state (like locking).

    The Server also exposes a websocket connection for the client to get immediate message updates from chats they are a part of.

    Fields:
        - max_users (int): The number beyond which no new users can register (w/out another user being deleted)
        - autosave (bool): [Not Implemented Yet] The server will periodically (`self.frequency`) save state or not
        - frequency (int): In minutes how frequently the server should autosave state
        - app (FastAPI): The FastAPI that powers this whole d@mn thing
        - users (dict[str, User]): The users that have been registered to the server
        - active_users (dict[str, WebSocket]): Active websocket connections (username protected)
        - chats (dict[str, Chat]): The chats that have been created in the server
        - logger (Logger): Utility to console out info or warnings to the command line
        - locked (bool): Whether the server is locked from receiveing new user registration or not (username protected)
    """
    def __init__(self, max_users: int, autosave: bool, frequency: int | None):
        self.max_users = max_users
        self.autosave = autosave
        self.frequency = frequency
        self.app = FastAPI()
        self.users: dict[str, User] = {}
        self.active_users: dict[str, WebSocket] = {}
        self.chats: dict[str, Chat] = {}
        self.logger = logging.getLogger(name="uvicorn")
        self.locked = False

    def run(self):
        """
        Exectution and hosting of the server. First Registers all routes and then runs via `uvicorn`
        """
        self.routes()
        uvicorn.run(self.app, host="0.0.0.0", port=5000)

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

            host = request.client.host
            server_port = request.scope.get("server")[1]
            response = {
                "http_url": f"http://{host}:{server_port}",
                "ws_url": f"ws://{host}:{server_port}/ws",
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

            new_user = User(username=username, uuid=uuid4())
            self.users[username] = new_user
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=f"New User [{username}] added with uuid: {new_user.uuid}",
            )

        @self.app.websocket("/ws")
        async def connect_user(websocket: WebSocket) -> JSONResponse:
            """
            Creates a websocket connection with the requesting client, and stores socket in active_users

            Fails:
                - If username is unrecognized
            """
            await websocket.accept()
            username = websocket.query_params.get("username", None)
            if username not in self.users:
                await websocket.close(code=1008, reason=f'User [{username}] Not Found in Server')
                return

            self.active_users[username] = websocket
            self.logger.info(f"Added User {username} to active users")

            try:
                while True:
                    data = await websocket.receive_text()
                    print(f"Received from {username}: {data}")
            except Exception as e:
                print(f"Connection with {username} lost: {e}")
            finally:
                del self.active_users[username]

        @self.app.post("/make_chat/{chatname}")
        async def make_chat(chatname: str, users: list[str]) -> JSONResponse:
            """
            Creates a chat in the server for the given users

            Fails:
                - If chatname already exists
                - If any user in users is unrecognized by server
            """
            if chatname in self.chats:
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content=f"Chat [{chatname}] Already Exists",
                )

            invalid_users = [user for user in users if user not in self.users]
            if invalid_users:
                return JSONResponse(
                    status_code=status.HTTP_406_NOT_ACCEPTABLE,
                    content=f"Users [{invalid_users}] Not Present in Server, Cannot be Added to Chat",
                )

            chat_users = set([self.users[user].username for user in users])
            new_chat = Chat(name=chatname, users=chat_users)
            self.chats[chatname] = new_chat
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
            for user in self.chats[destination].users:
                if user in self.active_users:
                    await self.active_users[user].send_text(message.content)
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
            return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                                content='Server Locked')

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
