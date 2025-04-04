import grpc
import threading
import time
import sys
import readchar

from gen.python import game_pb2
from gen.python import game_pb2_grpc # If needed in that file


SERVER_ADDRESS = "localhost:50051" # Server address and port

# --- Global variable to hold the latest input direction ---
# This is a simple way for the main thread to signal the sending logic
# More robust implementations might use queues or other synchronization
latest_input = game_pb2.PlayerInput.Direction.UNKNOWN
input_lock = threading.Lock()

def listen_for_updates(stub, send_input_func):
    """
    Listens for GameState updates from the server stream in a separate thread.
    Also handles sending PlayerInput messages periodically or on change.
    """
    global latest_input
    print("Connecting to stream...")
    try:
        # --- Start the bidirectional stream ---
        # We need to send *something* initially, or structure it to wait
        # Let's send an initial UNKNOWN input to kick things off
        def input_generator():
            global latest_input
            last_sent_input = None
            while True:
                # Simple logic: Send input if it changed, or periodically?
                # Let's send if it changed since last time.
                current_input_to_send = game_pb2.PlayerInput.Direction.UNKNOWN
                with input_lock:
                    current_input_to_send = latest_input
                    # Reset latest input after reading to avoid re-sending immediately?
                    # Or just send current state? Let's just send current state.

                if current_input_to_send != last_sent_input:
                     print(f"DEBUG: Sending input {game_pb2.PlayerInput.Direction.Name(current_input_to_send)}")
                     yield game_pb2.PlayerInput(direction=current_input_to_send)
                     last_sent_input = current_input_to_send
                else:
                    # Send infrequent keep-alive or allow server to timeout?
                    # Let's just yield nothing if no change for now, might need keep-alive later.
                     pass # yield game_pb2.PlayerInput(direction=game_pb2.PlayerInput.Direction.UNKNOWN) ?

                time.sleep(0.1) # Adjust sleep time as needed (controls input send rate)


        stream = stub.GameStream(input_generator())
        print("Stream started. Waiting for game state updates...")

        # --- Receive Loop ---
        for state in stream:
            print("\n--- Game State Update ---")
            if not state.players:
                print("No players in game.")
            else:
                for player in state.players:
                    # Simple print representation
                    print(f"  Player {player.id}: Pos({player.x_pos:.1f}, {player.y_pos:.1f})")
            print("-------------------------")

    except grpc.RpcError as e:
        print(f"Error receiving game state: {e.code()} - {e.details()} - {e.debug_error_string()}")
    except Exception as e:
        print(f"An unexpected error occurred in listener thread: {e}")
    finally:
        print("Listener thread finished.")
        # Signal main thread to exit? Or just let it detect the closure.


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
    """Connects to the server and starts the communication threads."""
    print(f"Attempting to connect to server at {SERVER_ADDRESS}...")
    try:
        # Insecure channel for local testing
        channel = grpc.insecure_channel(SERVER_ADDRESS)
        # Add credentials here for secure connection:
        # credentials = grpc.ssl_channel_credentials(root_certificates=None) # Add certs
        # channel = grpc.secure_channel(SERVER_ADDRESS, credentials)

        # Check connection (optional, makes startup faster to detect failure)
        try:
             grpc.channel_ready_future(channel).result(timeout=5) # 5 second timeout
             print("Channel connected.")
        except grpc.FutureTimeoutError:
             print(f"Error: Connection timed out after 5 seconds. Is the server running at {SERVER_ADDRESS}?")
             return

        stub = game_pb2_grpc.GameServiceStub(channel)

        # Start listener thread (which also handles sending)
        # Pass the stub and the send function reference? Or handle send within listener?
        # Let's handle sending within the listener thread via the generator.
        listener_thread = threading.Thread(target=listen_for_updates, args=(stub, None), daemon=True)
        listener_thread.start()

        # Start input handling in the main thread
        handle_input()

        # Wait for listener thread to potentially finish (e.g., on error)
        # Or just exit when handle_input finishes (ESC pressed)
        listener_thread.join(timeout=1.0) # Wait briefly for thread cleanup

    except Exception as e:
        print(f"Failed to connect or run client: {e}")
    finally:
        if 'channel' in locals() and channel:
            channel.close()
        print("Client shut down.")

if __name__ == "__main__":
    run()