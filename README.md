# Simple gRPC Game Demo

## Description

This project is a basic demonstration of a real-time 2D multiplayer game architecture using gRPC bidirectional streaming. It features an authoritative server written in Go and a graphical client written in Python using Pygame. The focus is on demonstrating client-server communication, state synchronization using delta updates, and basic game mechanics like movement and collision.

## Features

* **Real-time Multiplayer:** Supports multiple clients connecting simultaneously.
* **gRPC Bidirectional Streaming:** Efficient, low-latency communication between client and server.
* **Authoritative Go Server:** Server manages game state, physics, and validation.
* **Python/Pygame Client:** Renders the game visually and handles user input.
* **Protocol Buffers:** Defines the communication contract between client and server.
* **Delta Updates:** Server sends only state changes to clients for efficient synchronization.
* **Map Loading:** Server loads a simple tile map from `map.txt`.
* **Collision Detection:** Basic server-side collision detection against map walls and other players.
* **Configurable Server:** Server IP address and port can be set via command-line flags.
* **Automated Client Build:** Includes a GitHub Actions workflow to build a standalone Windows executable for the client.

## Technology Stack

* **Server:** Go (Go 1.21+ recommended for `maps.Clone`)
* **Client:** Python (Python 3.9+ recommended), Pygame
* **Communication:** gRPC, Protocol Buffers v3
* **Build (Client):** PyInstaller, GitHub Actions

## Project Structure

```txt
.
├── client/               # Python client source code
│   ├── assets/           # Client assets (images, etc.)
│   ├── client.py         # Main Pygame client application
│   ├── requirements.txt  # Python dependencies
│   └── create_sprite.py  # (Optional) Script to generate player sprite
├── gen/                  # Generated gRPC/Protobuf code
│   ├── go/game/          # Generated Go code
│   └── python/           # Generated Python code
├── server/               # Go server source code
│   ├── cmd/server/       # Main server application
│   │   └── main.go
│   └── internal/game/    # Core game state logic
│       └── state.go
├── .github/workflows/    # GitHub Actions workflows
│   └── build-windows-client.yml
├── game.proto            # Protocol Buffers definition file
├── go.mod                # Go module definition
├── go.sum                # Go module checksums
└── map.txt               # Game map definition
```

## Setup & Prerequisites

1.  **Go:** Install Go (version 1.21 or later recommended). [https://go.dev/doc/install](https://go.dev/doc/install)
2.  **Python:** Install Python (version 3.9 or later recommended). [https://www.python.org/downloads/](https://www.python.org/downloads/)
3.  **Protocol Buffer Compiler:** Install `protoc`. [https://grpc.io/docs/protoc-installation/](https://grpc.io/docs/protoc-installation/)
4.  **Go gRPC Plugins:** Install the Go code generator plugins:
    ```bash
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.28
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.2
    # Ensure your $GOPATH/bin is in your system's PATH
    ```
5.  **Python gRPC Tools:** Install the Python dependencies, including gRPC tools:
    ```bash
    pip install -r client/requirements.txt
    ```
    *(Note: `requirements.txt` should include `grpcio`, `grpcio-tools`, `protobuf`, `pygame`)*

## Generating gRPC Code

If you modify `game.proto`, you need to regenerate the Go and Python code. Run the following command from the project root directory:

```bash
protoc --proto_path=proto \                                                                                                                                                                                                                                                    ─╯
       --go_out=./gen/go/game --go_opt=paths=source_relative \
       --go-grpc_out=./gen/go/game --go-grpc_opt=paths=source_relative \
       proto/game.proto
```
(Ensure protoc, protoc-gen-go, protoc-gen-go-grpc, and the Python plugins are accessible in your PATH)Running the ProjectRun the Server:Open a terminal in the project root.# Run with default IP/Port (check main.go for defaults)
```shell
go run ./server/cmd/server/main.go
```

# Or specify IP and Port
```shell
go run ./server/cmd/server/main.go -ip 0.0.0.0 -port 50055
Run the Client:Important: Ensure the SERVER_ADDRESS constant near the top of client/client.py matches the IP and port the server is listening on.Open another terminal in the project root.python client/client.py
You can run multiple client instances to see the multiplayer aspect.Building the Client (Windows)A GitHub Actions workflow is included in .github/workflows/build-windows-client.yml. When changes are pushed to the main branch (or triggered manually):The workflow runs on a Windows environment.It installs Python, dependencies, and PyInstaller.It builds client/client.py into a single executable (GameClient.exe) using PyInstaller, bundling assets and generated code.The executable is uploaded as a workflow artifact named GameClient-Windows, which can be downloaded from the Actions tab on GitHub.*(Manual build: You can run the pyinstaller command from
```