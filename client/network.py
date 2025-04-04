# client/network.py
import grpc
import threading
import time
import queue
import sys

try:
    from gen.python import game_pb2        # <-- Import 1
    from gen.python import game_pb2_grpc  # <-- Import 2
except ModuleNotFoundError as e:
    print(f"network.py: Error importing generated code. Did you run 'protoc' and create gen/__init__.py / gen/python/__init__.py? Error: {e}")
    game_pb2 = None
    game_pb2_grpc = None
    sys.exit(1)

# Import state manager only for type hinting (optional)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .state import GameStateManager


class NetworkHandler:
    """Handles gRPC communication in a separate thread."""

    def __init__(self, server_address: str, state_manager: 'GameStateManager', incoming_queue: queue.Queue):
        self.server_address = server_address
        self.state_manager = state_manager  # Used only for setting connection errors
        # Queue to send received messages to main thread
        self.incoming_queue = incoming_queue
        self.outgoing_queue = queue.Queue()  # Queue for main thread to send messages (chat)
        self.input_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.direction_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.stub = None
        self.channel = None
        self._username_to_send = "Player"
        self._stream_started = threading.Event()

    def set_username(self, username: str):
        """Sets the username to be sent in ClientHello."""
        self._username_to_send = username if username else "Player"

    def _message_generator(self):
        """Generator yields ClientHello, then messages from outgoing_queue, then PlayerInput."""
        try:
            # 1. Send ClientHello
            print(
                f"NetHandler GEN: Sending ClientHello for '{self._username_to_send}'")
            hello_msg = game_pb2.ClientHello(
                desired_username=self._username_to_send)
            yield game_pb2.ClientMessage(client_hello=hello_msg)
            print("NetHandler GEN: ClientHello sent.")
            self._stream_started.set()

            # 2. Send other messages (Chat first, then Input)
            while not self.stop_event.is_set():
                outgoing_msg_to_yield = None
                try:
                    # Check for priority messages (like chat) first, non-blocking
                    retrieved_item = self.outgoing_queue.get_nowait()

                    if isinstance(retrieved_item, game_pb2.ClientMessage):
                        outgoing_msg_to_yield = retrieved_item
                        # print(f"NetHandler GEN: Found ClientMessage in outgoing queue!") # Verbose log
                    else:
                        print(
                            f"NetHandler GEN: Error - Unexpected item type in outgoing queue: {type(retrieved_item)}")
                        raise queue.Empty  # Fallback

                except queue.Empty:
                    # No priority message OR unexpected type found, send current player input
                    with self.direction_lock:
                        dir_to_send = self.input_direction
                    input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                    outgoing_msg_to_yield = game_pb2.ClientMessage(
                        player_input=input_msg)

                except Exception as e:
                    print(
                        f"NetHandler GEN OutQueue Err: Type={type(e).__name__}, Msg='{e}'")
                    # Fallback to sending input
                    with self.direction_lock:
                        dir_to_send = self.input_direction
                    input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                    outgoing_msg_to_yield = game_pb2.ClientMessage(
                        player_input=input_msg)

                if outgoing_msg_to_yield:
                    msg_type = outgoing_msg_to_yield.WhichOneof(
                        'payload')  # Use correct oneof name
                    # print(f"NetHandler GEN: Yielding ClientMessage containing '{msg_type}'") # Verbose log
                    yield outgoing_msg_to_yield
                # else: This case should not be reachable now

                # Prevent busy-waiting
                time.sleep(1.0 / 30.0)  # Approx 30Hz

        except Exception as e:
            # Catch errors during initial yield or loop setup
            print(f"NetHandler GEN: Unhandled error in generator: {e}")
            self.stop_event.set()  # Stop the handler if generator fails
            # Potentially signal error to main thread more directly here

    def _listen_for_updates(self):
        """The main loop for the network thread."""
        print("NetHandler: Connecting...")
        try:
            # Create stream using the generator
            stream = self.stub.GameStream(self._message_generator())
            print("NetHandler: Stream started.")

            # Process incoming messages from server
            for message in stream:
                if self.stop_event.is_set():
                    break
                if message.HasField("initial_map_data"):
                    self.incoming_queue.put(
                        ("map_data", message.initial_map_data))
                elif message.HasField("delta_update"):
                    self.incoming_queue.put(
                        ("delta_update", message.delta_update))
                elif message.HasField("chat_message"):
                    self.incoming_queue.put(("chat", message.chat_message))

        except grpc.RpcError as e:
            # Handle gRPC specific errors (connection loss, etc.)
            if not self.stop_event.is_set():
                error_msg = f"gRPC Connection Error: {e.code()} - {e.details()}"
                print(error_msg)
                self.state_manager.set_connection_error(error_msg)
                self.stop_event.set()  # Signal main thread
            # else: Stop event already set, likely intentional shutdown
        except Exception as e:
            # Catch other unexpected errors in the listener loop
            if not self.stop_event.is_set():
                import traceback
                traceback.print_exc()
                error_msg = f"Network Listener Error: {e}"
                print(error_msg)
                self.state_manager.set_connection_error(error_msg)
                self.stop_event.set()
        finally:
            print("NetHandler: Listener finished.")
            self._stream_started.clear()  # Clear stream readiness signal
            self.stop_event.set()  # Ensure stop is set on any exit path

    def send_chat_message(self, text: str):
        """Queues a chat message to be sent to the server."""
        if self._stream_started.is_set() and text:
            chat_req = game_pb2.SendChatMessageRequest(message_text=text)
            client_msg = game_pb2.ClientMessage(send_chat_message=chat_req)
            # print(f"NetHandler SEND: Putting chat: '{text[:30]}...'") # Verbose log
            self.outgoing_queue.put(client_msg)
            # print(f"NetHandler SEND: OutQueue size: {self.outgoing_queue.qsize()}") # Verbose log
        elif not text:
            print("NetHandler SEND: Ignoring empty chat message.")
        else:
            print("NetHandler SEND: Cannot send chat, stream not ready.")

    def start(self) -> bool:
        """Connects to the server and starts the network thread."""
        print(f"NetHandler: Attempting to connect to {self.server_address}...")
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("NetHandler: Channel connected.")
            self.stub = game_pb2_grpc.GameServiceStub(self.channel)
            self.stop_event.clear()
            self._stream_started.clear()
            self.thread = threading.Thread(
                target=self._listen_for_updates, daemon=True)
            self.thread.start()
            print("NetHandler: Listener thread started.")
            return True
        except grpc.FutureTimeoutError:
            err_msg = f"Timeout connecting to {self.server_address}"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            if self.channel:
                self.channel.close()  # Close channel if created
            return False
        except Exception as e:
            err_msg = f"Connection error: {e}"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            if self.channel:
                self.channel.close()  # Close channel if created
            return False

    def stop(self):
        """Signals the network thread to stop and cleans up resources."""
        print("NetHandler: Stopping...")
        self.stop_event.set()  # Signal generator and listener loops
        if self.channel:
            print("NetHandler: Closing channel...")
            self.channel.close()
            self.channel = None
        if self.thread and self.thread.is_alive():
            print("NetHandler: Joining thread...")
            self.thread.join(timeout=1.0)  # Wait briefly for thread exit
            if self.thread.is_alive():
                print("NetHandler: Warning - Listener thread did not exit cleanly.")
        print("NetHandler: Stopped.")

    def update_input_direction(self, new_direction):
        """Thread-safely updates the movement direction to be sent."""
        # Only update if the stream has been started (ClientHello sent)
        if self._stream_started.is_set():
            with self.direction_lock:
                if self.input_direction != new_direction:
                    self.input_direction = new_direction
