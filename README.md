# chatbois
chatbois is an *extremely* simple chat service built on top of [FastAPI](https://fastapi.tiangolo.com/), [Typer](https://typer.tiangolo.com/) (so I really owe [Sebastian](https://x.com/tiangolo) a beer), and [Rich](https://rich.readthedocs.io/en/latest/introduction.html).

chatbois is currently only tested on MacOS (though I suspect it would also work correctly on Linux [Windows folk, proceed at your own risk]).

Architecturally, the server is ***heavy*** in that it is the SOT (Source of Truth) for all state, and the client is merely a renderer of that state for the user. The security is... minimal at best... in that each user has a UUID assigned to them by the server, which is used for validating what user is accessing what chats and messages, etc. This would not be hard to beef up if you wanted to.

Here's a screaming detail that anyone will notice. There's no DB. Why? Because I only know file I/O and not the faintest about databases. This also should be relatively easy to upgrade in your own version of the project if you would like.

### Current Scope
- Stand up a central server (via `./chatbois --server`) either new or restarting an existing server
- Register and connect clients (via `./chatbois`) over a FastAPI WebSocket
- Chat creation/management
- Sending/Receiving Messages

### Future Features
- The Client is still missing a lot of handles over the server
- There's likely a usecase for adding a `perms` Enum to the `User` class so only particular kinds of users can initialize certain actions (like Locking/Unlocking the server)
- Friendlier UI: There's some clunkiness, and integrating `keyboard` in would likely make the UX a lot better
- Database persistence rather than periodic saving to files
- A `user_trie` data structure on the server to give a nice autocompletion-style interaction when adding users to a chat
- General clean-up: Adding more docstrings and trimming memory fat on both the server and client side
- Server Migration (in the case that your server has been compromised in some way)
- ASCII Art representations of Images/GIFs/Videos/etc.
- Peer to Peer Messaging where the Central server is merely an address bookkeeper

All in all, at this early stage, chatbois is basically a toy project, but could be very fun to add to over time.

## Installation
1. Clone the repo on the server machine (can be the same as a client machine)
2. Create a virtual environment with your tool of choice (example: `python3 -m venv venv`)
3. Install all dependencies via `pip install -r requirements.txt`
4. Add executible privaleges to the project `chmod +x chatbois`
5. Instantiate your server with `./chatbois.py --server`
6. Instantiate your client with `./chatbois.py`
7. Invite your bois and chat
