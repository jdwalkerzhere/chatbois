from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class User(BaseModel):
    IP_Address: str
    username: str
    id: int


class Message(BaseModel):
    sender: User
    chat: Chat
    content: str | None = None


class Chat(BaseModel):
    uuid: int
    users: list[User] | None = None
    messages: list[Message] | None = None


class Server(BaseModel):
    IP_Address: str
    users: set[User]
    chats: dict[int, Chat]


stuff_dict: dict[str, str] = {'hey': 'how you doin?'}


def some_num() -> int:
    return 5


@app.get("/{messages}")
async def root(messages: str):
    if messages in stuff_dict:
        return {'message': stuff_dict[messages],
                'value': some_num() + 1}
    return {"message": messages,
            "value": some_num()}
