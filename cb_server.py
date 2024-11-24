from __future__ import annotations
import logging
from typing import Annotated
from fastapi import Body, FastAPI, Request, WebSocket, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, BaseModel
from uuid import uuid4
import uvicorn


class User(BaseModel):
    username: str
    uuid: UUID4


class Message(BaseModel):
    sender: str
    dest: str
    content: str


class Chat(BaseModel):
    name: str
    users: set[str]
    history: list[Message] = []


class ChatboisServer:
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
        self.routes()
        uvicorn.run(self.app, host="0.0.0.0", port=5000)

    def routes(self):
        @self.app.get("/info")
        async def info(request: Request) -> JSONResponse:
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
            await websocket.accept()
            username = websocket.query_params.get("username", None)
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=f"User [{username}] Not Present in Server.",
                )

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
            if username not in self.users:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content=f"Non-member User Cannot Lock Server",
                )

            self.locked = True

        @self.app.post("/unlock_server")
        async def unlock_server(username: str) -> JSONResponse:
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
