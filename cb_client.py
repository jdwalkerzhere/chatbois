import asyncio
from pydantic import BaseModel, HttpUrl, WebsocketUrl
from websockets import connect, ConnectionClosedError


class ClientServer(BaseModel):
    username: str
    HttpURL: HttpUrl
    WebsocketUrl: WebsocketUrl


class ChatboisClient:
    def __init__(self, servers: list[ClientServer]):
        self.servers = servers

    async def connect(self, server: ClientServer):
        async with connect(
            f"{server.WebsocketUrl}?username={server.username}"
        ) as websocket:
            try:
                while True:
                    response = await websocket.recv()
            except ConnectionClosedError as e:
                print(f"Connection closed: {e}")

    async def run(self):
        tasks = [self.connect(server) for server in self.servers]
        await asyncio.gather(*tasks)
