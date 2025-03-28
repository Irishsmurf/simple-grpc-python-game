import grpc
import threading
import time
import sys
import readchar
import pygame

# Import generated code (assuming 'gen/python' is accessible)
# Adjust sys.path if your structure differs or use package installation
import sys
import os
# Add the parent directory ('simple-grpc-game') to sys.path to find 'gen'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from gen.python import game_pb2
    from gen.python import game_pb2_grpc
except ModuleNotFoundError as e:
    print(e)
    print("Error: Could not find generated Proto/gRPC Python code.")
    print("Ensure 'protoc' was run correctly and 'gen/python' is in the Python path.")
    sys.exit(1)


SERVER_ADDRESS = "localhost:50051" # Server address and port
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50) # Dark blue
PLAYER_SPRITE_PATH = "assets/player.png"
FPS = 60

latest_game_state = None
state_lock = threading.Lock()

current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
direction_lock = threading.Lock()


def listen_for_updates(stub, send_input_func):
    """
    Listens for GameState updates from the server stream in a separate thread.
    Also handles sending PlayerInput messages periodically or on change.
    """
    global latest_game_state
    print("Connecting to stream...")
    try:
        # --- Start the bidirectional stream ---
        # We need to send *something* initially, or structure it to wait
        # Let's send an initial UNKNOWN input to kick things off
        def input_generator():
            global latest_input
            global current_direction
            last_sent_direction = None
            while True:
                # Simple logic: Send input if it changed, or periodically?
                # Let's send if it changed since last time.
                dir_to_send = game_pb2.PlayerInput.Direction.UNKNOWN
                with direction_lock:
                    dir_to_send = current_direction
                yield game_pb2.PlayerInput(direction=dir_to_send)

                time.sleep(0.1 / 30.0) # Adjust sleep time as needed (controls input send rate)


        stream = stub.GameStream(input_generator())
        print("Stream started. Waiting for game state updates...")

        # --- Receive Loop ---
        for state in stream:
            print("\n--- Game State Update ---")
            with state_lock:
                latest_game_state = state
            player_ids = [p.id for p in state.players] if state and state.players else []
            print(f"DEBUG Listener: Received state update with player IDs: {player_ids}")


    except grpc.RpcError as e:
        print(f"Error receiving game state: {e.code()} - {e.details()} - {e.debug_error_string()}")
    except Exception as e:
        print(f"An unexpected error occurred in listener thread: {e}")
    finally:
        print("Listener thread finished.")

def handle_input():
    """Handles keyboard input to set the direction using readchar."""
    global latest_input
    print("Input handler started. Use W, A, S, D to move. Press 'q' to exit.") # Changed exit key

    while True:
        try:
            # Read a single character without waiting for Enter
            key = readchar.readkey()

            new_input = game_pb2.PlayerInput.Direction.UNKNOWN
            key_lower = key.lower() # Check lowercase

            if key_lower == 'w':
                new_input = game_pb2.PlayerInput.Direction.UP
            elif key_lower == 's':
                new_input = game_pb2.PlayerInput.Direction.DOWN
            elif key_lower == 'a':
                new_input = game_pb2.PlayerInput.Direction.LEFT
            elif key_lower == 'd':
                new_input = game_pb2.PlayerInput.Direction.RIGHT
            elif key_lower == 'q': # Use 'q' to quit cleanly
                 print("'q' pressed, exiting...")
                 # How to signal exit? Maybe set a global flag or break loop
                 # For now, just break, the finally block in run() will close channel
                 break
            # else: input is ignored

            # --- Update latest_input (thread-safe) ---
            # Send direction on press, maybe send UNKNOWN on any other key?
            # This logic doesn't handle key *release* like the keyboard lib did.
            # It just sends the last direction pressed. Needs refinement for stopping.
            with input_lock:
                if latest_input != new_input:
                    print(f"Input: {key_lower} -> {game_pb2.PlayerInput.Direction.Name(new_input)}")
                    latest_input = new_input
                # Maybe set to UNKNOWN if key is not WASD?
                elif new_input == game_pb2.PlayerInput.Direction.UNKNOWN and latest_input != game_pb2.PlayerInput.Direction.UNKNOWN:
                     print(f"Input cleared (non-WASD key: {key})")
                     latest_input = game_pb2.PlayerInput.Direction.UNKNOWN


        except Exception as e:
            print(f"Error reading input: {e}")
            break # Exit loop on error

    print("Input handler finished.")

def run():
    global latest_game_state
    global current_direction

    pygame.init()
    pygame.display.set_caption("Simple gRPC Game Client")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    # Load Assets
    try:
        player_img = pygame.image.load(PLAYER_SPRITE_PATH).convert_alpha()
        player_rect = player_img.get_rect()
        print(f"Loaded player sprite from {PLAYER_SPRITE_PATH}")
    except pygame.error as e:
        print(f"Error loading player sprite: {e}")
        print("Ensure the asset path is correct and the file exists.")
        pygame.quit()
        return
    
    channel = None
    listener_thread = None
    print(f"Attempting to connect to server at {SERVER_ADDRESS}...")
    try:
        channel = grpc.insecure_channel(SERVER_ADDRESS)
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
            print("Channel connected.")
        except grpc.FutureTimeoutError:
            print(f"Error: Connection timed out after 5 seconds. Is the server running at {SERVER_ADDRESS}?")
            raise
        stub = game_pb2_grpc.GameServiceStub(channel)
        listener_thread = threading.Thread(target=listen_for_updates, args=(stub, None), daemon=True)
        listener_thread.start()
        print("Listener thread started.")

        # Main loop
        running = True
        while running:
            new_direction = game_pb2.PlayerInput.Direction.UNKNOWN
            keys_pressed = pygame.key.get_pressed()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]:
                new_direction = game_pb2.PlayerInput.Direction.UP
            elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]:
                new_direction = game_pb2.PlayerInput.Direction.DOWN
            elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]:
                new_direction = game_pb2.PlayerInput.Direction.LEFT
            elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]:
                new_direction = game_pb2.PlayerInput.Direction.RIGHT

            with direction_lock:
                if current_direction != new_direction:
                    current_direction = new_direction
                    print(f"Direction changed to {game_pb2.PlayerInput.Direction.Name(current_direction)}")
            
            screen.fill(BACKGROUND_COLOR)

            # Draw the player sprite at the current position
            current_state_snapshot = None
            with state_lock:
                snapshot_read_debug = latest_game_state
                if latest_game_state is not None:
                    current_state_snapshot = latest_game_state
            if current_state_snapshot:
                for player in current_state_snapshot.players:
                    pos_x = int(player.x_pos)
                    pos_y = int(player.y_pos)
                    player_rect.center = (pos_x, pos_y)
                    screen.blit(player_img, player_rect)
            
            pygame.display.flip()
            clock.tick(FPS)

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()} - {e.debug_error_string()}")
    except Exception as e:
        print(f"An error occurred in the main loop or connection: {e}")
    finally:
        if channel:
            channel.close()
        pygame.quit()
        if listener_thread and listener_thread.is_alive():
            print("Waiting for listener thread to finish...")
            listener_thread.join(timeout=0.5)
        pygame.quit()
        print("Client shut down.")

if __name__ == "__main__":
    run()