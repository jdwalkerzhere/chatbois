import asyncio
from json import loads
from os import listdir
from pydantic import BaseModel, HttpUrl, WebsocketUrl
import requests
from rich.prompt import IntPrompt, Confirm, Prompt

import typer

from cb_server import ChatboisServer
from cb_client import ChatboisClient



class ServerConfig(BaseModel):
    """
    Simple Server Configuration for the chatbois Server

    Fields:
        - max_users (int): The number beyond which the server stops accepting new user registration requests
        - autosave (Autosave): Whether the server should automatically save on its own at a cadence
    """

    max_users: int
    autosave: bool
    frequency: int | None


class ClientServer(BaseModel):
    """
    ClientServer is used to populate the ClientConfig class.

    This class's fields are populated either by reading from the `client_config.json` or from a call to `build_client_config`.

    Fields:
        - username: the name that the ChatboisServer recognizes the user by
        - HttpURL: the HTTP URL that the ChatboisServer you're connecting to is running at
        - WebsocketUrl: The Websocket URL that the ChatboisServer the user is connectiging to is running at
    """
    username: str
    HttpURL: HttpUrl
    WebsocketUrl: WebsocketUrl


class ClientConfig(BaseModel):
    """
    The list of servers that the ChatboisClient can connect to
    """
    servers: list[ClientServer]


def build_server_config() -> ServerConfig:
    """
    In the case that no `server_config.json` exists, the user is prompted for their preferred settings

    Returns:
        - server_config (ServerConfig): Pydantic Model for the settings the chatboi's server will read from.
    """
    max_users = IntPrompt.ask(
        "What is the maximum number of users this server will support?"
    )
    autosave = Confirm.ask(
        "Would you like this server to periodically save state? (Otherwise state is self-managed)"
    )
    frequency = None
    if autosave:
        frequency = IntPrompt.ask(
            "How frequently (in minutes) do you want the server to autosave?: "
        )
    server_config = ServerConfig(
        max_users=max_users, autosave=autosave, frequency=frequency
    )
    return server_config


def build_client_config() -> ClientConfig:
    """
    Called when no `client_config.json` is found in the root directory to read from.

    Consecutively asks what servers the user wants to be added to, if they are an existing user, and registers them if not.

    Returns:
        - client_config (ClientConfig): Used to start the Chatbois Client
    """
    servers = []
    while True:
        server_to_add = Confirm.ask("Do You Want to Add a Server?")
        if not server_to_add:
            break

        server_http_address = Prompt.ask("What Address is the Server Running at?")
        urls = requests.get(f"{server_http_address}/info").json()
        http_url, ws_url = urls["http_url"], urls["ws_url"]
        registered = Confirm.ask("Have you Registered with this Server Yet?")
        if registered:
            username = Prompt.ask("What is your username for this server?")
        else:
            while True:
                username = Prompt.ask(
                    "What do you want your username to be for this Server?"
                )
                sucessful_register = requests.post(f"{http_url}/register/{username}")
                if sucessful_register.status_code == 202:
                    break

        servers.append(
            ClientServer(username=username, HttpURL=http_url, WebsocketUrl=ws_url)
        )

    return ClientConfig(servers=servers)


def start_client(client_config: ClientConfig) -> None:
    """
    Starts the ChatboisClient

    Reads from the `client_config` and establishes connections with all the live servers available
    """
    print("Starting ChatboisClient")
    client = ChatboisClient(servers=client_config.servers)
    asyncio.run(client.run())


def initialize_client() -> None:
    """
    Attempts to read from `client_config.json` and runs `build_client_config()` if it is not present.

    Eventually makes call to `start_client()` after the necessary configuration details have been gathered.
    """
    print("Initializing chatbois Client")
    if "client_config.json" not in listdir():
        print("No client config found, please configure.")
        client_config = build_client_config()
        with open("client_config.json", "w+") as new_client_config:
            new_client_config.write(client_config.model_dump_json())
            new_client_config.close()

    with open("client_config.json", "r") as client_options:
        client_options = loads(client_options.read())
        client_config = ClientConfig(**client_options)

    print("loading client config")
    start_client(client_config)


def start_server(server_config: ServerConfig) -> None:
    """
    Runs the FastAPI ChatboisServer with all the necessary configurations set.
    """
    max_users = server_config.max_users
    autosave = server_config.autosave
    frequency = server_config.frequency
    server = ChatboisServer(max_users=max_users, autosave=autosave, frequency=frequency)
    server.run()


cli = typer.Typer()


@cli.command()
def initialize_server(server: bool = False):
    """
    A Typer Optional command that determines whether to run the chatbois server or client logic

    The default behavior is that if you aren't running the chatbois' server you *are* running the
    chatbois' client.

    Arguments:
        server (bool): CLI flag `--server` meaning whether to run the chatbois server or client
    """
    if not server:
        initialize_client()
        return

    print("Initializing chatbois Server")
    if "server_config.json" not in listdir():
        print("No server config file found, please configure.")
        server_config = build_server_config()
        with open("server_config.json", "w+") as new_server_config:
            new_server_config.write(server_config.model_dump_json())
            new_server_config.close()

    with open("server_config.json", "r") as server_options:
        server_options = loads(server_options.read())
        server_config = ServerConfig(**server_options)

    print("Starting chatbois Server")
    start_server(server_config)


def main():
    """
    Single entrypoint to running either the ChatboisServer or ChatboisClient

    Which mode gets run is handled by the Typer `cli` app that is initialized immediately above `initialize_server()`
    """
    cli()


if __name__ == "__main__":
    main()
