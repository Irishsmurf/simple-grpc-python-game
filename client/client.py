import grpc
import threading
import time
import sys
import os
import pygame
from queue import Queue, Empty as QueueEmpty # Use Queue for state updates

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # The destination path used in --add-data becomes the relative path base here.
        base_path = sys._MEIPASS
    except Exception:
        # If not running in PyInstaller bundle, use the script's directory
        base_path = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(base_path, relative_path)

# --- Configuration ---
SERVER_ADDRESS = "192.168.41.108:50051" # Server address and port
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50) # Dark blue
PLAYER_SPRITE_PATH = "assets/player_large.png" # Fallback? Sprite sheet is used.
FRAME_WIDTH = 128
FRAME_HEIGHT = 128
FPS = 60

TILESET_PATH = resource_path("assets/tileset.png")
SPRITE_SHEET_PATH = resource_path("assets/player_sheet_256.png")

# --- Attempt to import generated code ---
# Add the parent directory ('simple-grpc-game') to sys.path to find 'gen'
# This is still not ideal, but better than modifying sys.path inside functions.
# A proper package setup or PYTHONPATH is recommended for larger projects.
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
gen_python_path = os.path.join(parent_dir, 'gen', 'python')
if gen_python_path not in sys.path:
    sys.path.insert(0, gen_python_path)
# Also add the parent dir itself if 'gen' is treated as a package relative to it
if parent_dir not in sys.path:
     sys.path.insert(0, parent_dir)

try:
    from gen.python import game_pb2
    from gen.python import game_pb2_grpc
except ModuleNotFoundError as e:
    print(f"Error importing generated code: {e}")
    print("sys.path:", sys.path)
    print("Attempted path:", gen_python_path)
    print("Ensure 'protoc' was run correctly and the 'gen/python' directory exists relative to the script's parent.")
    sys.exit(1)

# --- Color Palette ---
AVAILABLE_COLORS = [
    (255, 255, 0),   # Yellow (Original)
    (0, 255, 255),   # Cyan
    (255, 0, 255),   # Magenta
    (0, 255, 0),     # Green
    (255, 165, 0),   # Orange
    (255, 255, 255), # White
]

# --- Game State Manager ---
class GameStateManager:
    """Manages the game state received from the server."""
    def __init__(self):
        self.state_lock = threading.Lock()
        self.map_lock = threading.Lock()
        self.color_lock = threading.Lock()

        self.latest_game_state = None
        self.my_player_id = None
        self.connection_error_message = None

        # Map data
        self.world_map_data = None
        self.map_width_tiles = 0
        self.map_height_tiles = 0
        self.world_pixel_width = 0.0
        self.world_pixel_height = 0.0
        self.tile_size = 32 # Default, updated from server

        # Player appearance
        self.player_colors = {}
        self.next_color_index = 0

    def update_state(self, new_state):
        """Thread-safely updates the latest game state."""
        with self.state_lock:
            self.latest_game_state = new_state
            # Assign colors to new players
            with self.color_lock:
                for p in new_state.players:
                    if p.id not in self.player_colors:
                        self.player_colors[p.id] = AVAILABLE_COLORS[self.next_color_index % len(AVAILABLE_COLORS)]
                        self.next_color_index += 1

    def get_state_snapshot(self):
        """Thread-safely gets a copy of the latest game state."""
        with self.state_lock:
            # Return a direct reference for performance, assuming renderer won't modify.
            # If modification is needed, return a deep copy (more complex for protobuf).
            return self.latest_game_state

    def set_initial_map_data(self, map_proto):
        """Sets the initial map data and own player ID."""
        print(f"Received map data: {map_proto.tile_width}x{map_proto.tile_height} tiles")
        temp_map = []
        for y in range(map_proto.tile_height):
            row_proto = map_proto.rows[y]
            temp_map.append(list(row_proto.tiles))

        with self.map_lock:
            self.world_map_data = temp_map
            self.map_width_tiles = map_proto.tile_width
            self.map_height_tiles = map_proto.tile_height
            self.world_pixel_height = map_proto.world_pixel_height
            self.world_pixel_width = map_proto.world_pixel_width
            self.tile_size = map_proto.tile_size_pixels
            print(f"World size: {self.world_pixel_width}x{self.world_pixel_height} px, Tile size: {self.tile_size}")

        # Must set player ID outside map_lock but before returning control
        with self.state_lock:
            self.my_player_id = map_proto.assigned_player_id
            print(f"*** Received own player ID: {self.my_player_id} ***")


    def get_map_data(self):
        """Thread-safely gets map data."""
        with self.map_lock:
            # Return references - renderer shouldn't modify map data
            return self.world_map_data, self.map_width_tiles, self.map_height_tiles, self.tile_size

    def get_world_dimensions(self):
        """Gets world pixel dimensions."""
        with self.map_lock:
            return self.world_pixel_width, self.world_pixel_height

    def get_my_player_id(self):
        """Thread-safely gets the player's own ID."""
        with self.state_lock:
            return self.my_player_id

    def get_player_color(self, player_id):
        """Thread-safely gets the color for a player."""
        with self.color_lock:
            return self.player_colors.get(player_id, (255, 255, 255)) # Default white

    def get_all_player_colors(self):
        """Thread-safely gets a copy of the color map."""
        with self.color_lock:
            return self.player_colors.copy()

    def set_connection_error(self, error_msg):
        """Sets the connection error message."""
        with self.state_lock:
            self.connection_error_message = error_msg

    def get_connection_error(self):
        """Gets the current connection error message."""
        with self.state_lock:
            return self.connection_error_message

# --- Network Handler ---
class NetworkHandler:
    """Handles gRPC communication in a separate thread."""
    def __init__(self, server_address, state_manager, output_queue):
        self.server_address = server_address
        self.state_manager = state_manager
        self.output_queue = output_queue # Queue to send state updates to main thread
        self.input_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.direction_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.stub = None
        self.channel = None

    def _input_generator(self):
        """Generator function to send player input to the server."""
        while not self.stop_event.is_set():
            with self.direction_lock:
                dir_to_send = self.input_direction
            yield game_pb2.PlayerInput(direction=dir_to_send)
            # Adjust sleep time as needed (controls input send rate)
            # Consider sending only on change + periodic keepalive if needed
            time.sleep(1.0 / 30.0) # ~30 inputs per second

    def _listen_for_updates(self):
        """The main loop for the network thread."""
        print("NetworkHandler: Connecting to stream...")
        try:
            stream = self.stub.GameStream(self._input_generator())
            print("NetworkHandler: Stream started. Waiting for server messages...")

            # --- Receive Loop ---
            for message in stream:
                if self.stop_event.is_set():
                    break
                # Put received message onto the queue for the main thread
                self.output_queue.put(message)

        except grpc.RpcError as e:
            if not self.stop_event.is_set():
                error_msg = f"Connection Error: {e.code()} - {e.details()}. Try restarting Client/Server."
                print(f"NetworkHandler: Error receiving game state: {e.code()} - {e.details()}")
                self.state_manager.set_connection_error(error_msg)
                self.stop_event.set() # Signal main thread about the error
            else:
                print("NetworkHandler: Shutting down due to stop event (gRPC Cancel/Error)")
        except Exception as e:
            if not self.stop_event.is_set():
                import traceback
                traceback.print_exc()
                print(f"NetworkHandler: Unexpected error: {e}")
                self.state_manager.set_connection_error(f"Unexpected Network Error: {e}")
                self.stop_event.set() # Signal main thread
            else:
                 print("NetworkHandler: Shutting down due to stop event (Exception).")
        finally:
            print("NetworkHandler: Listener loop finished.")
            self.stop_event.set() # Ensure stop is set on exit

    def start(self):
        """Starts the network handler thread."""
        print(f"NetworkHandler: Attempting to connect to {self.server_address}...")
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            # Check if channel is ready (optional but good for quick failure)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("NetworkHandler: Channel connected.")
            self.stub = game_pb2_grpc.GameServiceStub(self.channel)

            self.stop_event.clear() # Ensure stop event is clear before starting
            self.thread = threading.Thread(target=self._listen_for_updates, daemon=True)
            self.thread.start()
            print("NetworkHandler: Listener thread started.")
            return True
        except grpc.FutureTimeoutError:
            err_msg = f"Error: Connection timed out after 5 seconds. Is the server running at {self.server_address}?"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            if self.channel:
                self.channel.close()
            return False
        except grpc.RpcError as e:
            err_msg = f"gRPC error during connection: {e.code()} - {e.details()}"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            if self.channel:
                self.channel.close()
            return False
        except Exception as e:
            err_msg = f"Unexpected error during connection: {e}"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            if self.channel:
                self.channel.close()
            return False


    def stop(self):
        """Signals the network thread to stop and closes the channel."""
        print("NetworkHandler: Stopping...")
        self.stop_event.set()
        if self.channel:
            print("NetworkHandler: Closing gRPC channel...")
            # Cancel the stream explicitly? Might help cleanup.
            # self.channel.close() might implicitly do this.
            self.channel.close()
            self.channel = None # Avoid trying to close again
        if self.thread and self.thread.is_alive():
            print("NetworkHandler: Waiting for listener thread to finish...")
            self.thread.join(timeout=1.0) # Wait max 1 second
            if self.thread.is_alive():
                print("NetworkHandler: Warning - Listener thread did not exit cleanly.")
        print("NetworkHandler: Stopped.")

    def update_input_direction(self, new_direction):
        """Thread-safely updates the direction to be sent."""
        with self.direction_lock:
            if self.input_direction != new_direction:
                self.input_direction = new_direction
                # print(f"NetworkHandler: Input direction set to {game_pb2.PlayerInput.Direction.Name(new_direction)}")


# --- Renderer ---
class Renderer:
    """Handles Pygame rendering and asset loading."""
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")

        # Fonts
        pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)

        # Assets
        self.directional_frames = {}
        self.tile_graphics = {}
        self.player_rect = None # Will be set based on loaded frame
        self.tile_size = 32 # Default, updated later

        self._load_assets()

        # Camera
        self.camera_x = 0.0
        self.camera_y = 0.0

    def _load_assets(self):
        """Loads game assets."""
        print("Renderer: Loading assets...")
        try:
            # Tileset (load first to get tile size if possible, though it's set later)
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha()
            print(f"Renderer: Loaded tileset from {TILESET_PATH}")
            # Initial tile graphic loading (assuming 32x32 tiles in tileset)
            # This might need adjustment if tile_size changes significantly later.
            self.tile_graphics[0] = tileset_img.subsurface((0, 0, self.tile_size, self.tile_size)) # Grass
            self.tile_graphics[1] = tileset_img.subsurface((self.tile_size, 0, self.tile_size, self.tile_size)) # Wall
            print(f"Renderer: Loaded {len(self.tile_graphics)} initial tile graphics (size {self.tile_size}x{self.tile_size}).")

            # Player Sprite Sheet
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
            print(f"Renderer: Loaded sprite sheet from {SPRITE_SHEET_PATH}")

            # Define frame rectangles based on constants
            up_rect = pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT)
            down_rect = pygame.Rect(FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT)
            left_rect = pygame.Rect(0, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
            right_rect = pygame.Rect(FRAME_WIDTH, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)

            # Extract frames
            self.directional_frames[game_pb2.AnimationState.RUNNING_UP] = sheet_img.subsurface(up_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN] = sheet_img.subsurface(down_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_LEFT] = sheet_img.subsurface(left_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_RIGHT] = sheet_img.subsurface(right_rect)
            # Use down-facing frame for idle/unknown states
            self.directional_frames[game_pb2.AnimationState.IDLE] = sheet_img.subsurface(down_rect)
            self.directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = sheet_img.subsurface(down_rect)

            print(f"Renderer: Extracted {len(self.directional_frames)} directional frames.")
            self.player_rect = self.directional_frames[game_pb2.AnimationState.IDLE].get_rect()

        except pygame.error as e:
            print(f"Renderer: Error loading assets: {e}")
            print("Ensure asset paths are correct and files exist.")
            # Consider raising the exception or setting an error state
            raise # Re-raise to stop initialization if assets fail

    def update_camera(self, target_x, target_y, world_width, world_height):
        """Updates the camera position based on the target (player)."""
        # Center camera on target
        target_cam_x = target_x - self.screen_width / 2
        target_cam_y = target_y - self.screen_height / 2

        # Clamp camera to world boundaries
        if world_width > self.screen_width:
            self.camera_x = max(0.0, min(target_cam_x, world_width - self.screen_width))
        else:
            # Center map if world is smaller than screen
            self.camera_x = (world_width - self.screen_width) / 2

        if world_height > self.screen_height:
            self.camera_y = max(0.0, min(target_cam_y, world_height - self.screen_height))
        else:
            # Center map if world is smaller than screen
            self.camera_y = (world_height - self.screen_height) / 2


    def draw_map(self, map_data, map_w, map_h, tile_size):
        """Draws the visible portion of the map."""
        if not map_data or tile_size <= 0:
            return

        # Update internal tile size if it changed
        if self.tile_size != tile_size:
             print(f"Renderer: Tile size changed to {tile_size}. Re-extracting tile graphics needed if tileset layout depends on it.")
             # TODO: Re-extract tile graphics if necessary, assuming tileset structure allows it.
             # For now, we assume the initial load was sufficient or the tileset is flexible.
             self.tile_size = tile_size


        # Calculate visible tile range with a buffer
        buffer = 1
        start_tile_x = max(0, int(self.camera_x / self.tile_size) - buffer)
        end_tile_x = min(map_w, int((self.camera_x + self.screen_width) / self.tile_size) + buffer + 1) # +1 for range end
        start_tile_y = max(0, int(self.camera_y / self.tile_size) - buffer)
        end_tile_y = min(map_h, int((self.camera_y + self.screen_height) / self.tile_size) + buffer + 1) # +1 for range end


        for y in range(start_tile_y, end_tile_y):
            if y >= len(map_data): continue # Bounds check
            for x in range(start_tile_x, end_tile_x):
                if x >= len(map_data[y]): continue # Bounds check

                tile_id = map_data[y][x]
                if tile_id in self.tile_graphics:
                    tile_surface = self.tile_graphics[tile_id]
                    screen_x = x * self.tile_size - self.camera_x
                    screen_y = y * self.tile_size - self.camera_y
                    self.screen.blit(tile_surface, (screen_x, screen_y))
                #else:
                #    print(f"Warning: Tile ID {tile_id} at ({x},{y}) not found in tile_graphics.")


    def draw_players(self, game_state, player_colors, my_player_id):
        """Draws the players."""
        if not game_state or not self.player_rect:
            return

        for player in game_state.players:
            player_state = player.current_animation_state
            # Use fallback (idle) frame if state is unknown or frame missing
            current_frame_surface = self.directional_frames.get(player_state, self.directional_frames[game_pb2.AnimationState.IDLE])

            if current_frame_surface:
                # Calculate screen position based on world position and camera
                screen_x = player.x_pos - self.camera_x
                screen_y = player.y_pos - self.camera_y

                # Center the player rect on the calculated screen position
                player_rect = current_frame_surface.get_rect()
                player_rect.center = (int(screen_x), int(screen_y))

                # Tinting logic
                temp_sprite_frame = current_frame_surface.copy()
                color = player_colors.get(player.id, (255, 255, 255)) # Default white
                # Create a tint surface (ensure it matches frame size)
                tint_surface = pygame.Surface(player_rect.size, pygame.SRCALPHA)
                tint_surface.fill(color + (128,)) # Apply tint with some alpha (e.g., 128 for 50% alpha)

                # Blit the tint surface onto the temporary sprite frame using BLEND_RGBA_MULT
                temp_sprite_frame.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)


                # Draw indicator for own player
                if player.id == my_player_id:
                    # Draw a white rectangle outline around the player
                    pygame.draw.rect(self.screen, (255, 255, 255), player_rect.inflate(4, 4), 2) # Inflate slightly for visibility

                # Blit the (potentially tinted) sprite frame
                self.screen.blit(temp_sprite_frame, player_rect)

    def draw_error_message(self, message):
        """Draws an error message centered on the screen."""
        error_surface = self.error_font.render(message, True, self.error_text_color)
        error_rect = error_surface.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
        self.screen.blit(error_surface, error_rect)

    def render(self, state_manager):
        """Main render loop."""
        # Check for connection errors first
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
        else:
            # Get current state and map data
            current_state = state_manager.get_state_snapshot()
            map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id()
            player_colors = state_manager.get_all_player_colors()

            # Update camera based on own player's position (if available)
            my_player_snapshot = None
            if current_state and my_player_id:
                for p in current_state.players:
                    if p.id == my_player_id:
                        my_player_snapshot = p
                        break
            if my_player_snapshot:
                 world_w, world_h = state_manager.get_world_dimensions()
                 self.update_camera(my_player_snapshot.x_pos, my_player_snapshot.y_pos, world_w, world_h)

            # --- Drawing ---
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_map(map_data, map_w, map_h, tile_size)
            self.draw_players(current_state, player_colors, my_player_id)

        # --- Update Display ---
        pygame.display.flip()

# --- Input Handler ---
class InputHandler:
    """Handles Pygame input events."""
    def __init__(self):
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False

    def handle_events(self):
        """Processes Pygame events and updates direction."""
        self.quit_requested = False # Reset quit request each frame
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_requested = True
                return # Exit event loop immediately on QUIT
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.quit_requested = True
                    return # Exit event loop immediately on ESC

        # Check pressed keys for movement (allows holding keys)
        keys_pressed = pygame.key.get_pressed()
        if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]:
            new_direction = game_pb2.PlayerInput.Direction.UP
        elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]:
            new_direction = game_pb2.PlayerInput.Direction.DOWN
        elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]:
            new_direction = game_pb2.PlayerInput.Direction.LEFT
        elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]:
            new_direction = game_pb2.PlayerInput.Direction.RIGHT

        # Update direction only if it changed
        if self.current_direction != new_direction:
            self.current_direction = new_direction
            # Optional: print direction change
            # print(f"InputHandler: Direction changed to {game_pb2.PlayerInput.Direction.Name(self.current_direction)}")

        return self.current_direction

    def should_quit(self):
        """Returns true if quit was requested."""
        return self.quit_requested


# --- Game Client ---
class GameClient:
    """Main game client class."""
    def __init__(self):
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.input_handler = InputHandler()
        self.clock = pygame.time.Clock()
        self.server_message_queue = Queue() # Queue for messages from network thread
        self.network_handler = NetworkHandler(SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False

    def _process_server_messages(self):
        """Processes messages received from the network thread."""
        try:
            while True: # Process all messages currently in the queue
                message = self.server_message_queue.get_nowait()
                if message.HasField("initial_map_data"):
                    self.state_manager.set_initial_map_data(message.initial_map_data)
                    # Update renderer's tile size if needed
                    _, _, _, tile_size = self.state_manager.get_map_data()
                    if self.renderer.tile_size != tile_size:
                         print(f"Client: Updating renderer tile size to {tile_size}")
                         self.renderer.tile_size = tile_size
                         # Potentially trigger re-extraction of tile graphics in renderer here
                elif message.HasField("game_state"):
                    self.state_manager.update_state(message.game_state)
                else:
                     print("Warning: Received unknown server message type")

        except QueueEmpty:
            pass # No more messages for now
        except Exception as e:
            print(f"Error processing server message queue: {e}")


    def run(self):
        """Main game loop."""
        self.running = True
        if not self.network_handler.start():
            print("Failed to start network handler. Exiting.")
            self.running = False # Ensure loop doesn't start if network failed
            # Display the error message set by network_handler.start()
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        pygame.quit()
                        return # Exit if user quits error screen
                self.renderer.render(self.state_manager) # Show error message
                self.clock.tick(10) # Low FPS for error screen


        # Wait briefly for player ID to arrive
        print("Waiting for player ID from server...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:
            self._process_server_messages() # Process messages while waiting
            if self.network_handler.stop_event.is_set(): # Check if network thread died
                 print("Network thread stopped while waiting for player ID. Exiting.")
                 self.running = False
                 break
            if time.time() - wait_start_time > 10: # Timeout waiting for ID
                 print("Error: Timed out waiting for player ID from server.")
                 self.state_manager.set_connection_error("Timed out waiting for player ID.")
                 self.running = False
                 break
            time.sleep(0.05)


        print("Starting main game loop...")
        while self.running:
            # Check for stop signals (e.g., network error)
            if self.network_handler.stop_event.is_set():
                print("Stop event detected from network thread. Exiting loop.")
                self.running = False
                continue

            # Handle Input
            current_direction = self.input_handler.handle_events()
            if self.input_handler.should_quit():
                self.running = False
                continue

            # Update network handler with latest input
            self.network_handler.update_input_direction(current_direction)

            # Process messages from server
            self._process_server_messages()

            # Render the current state
            self.renderer.render(self.state_manager)

            # Cap the frame rate
            self.clock.tick(FPS)

        # --- Cleanup ---
        print("Client: Exiting main loop.")
        self.shutdown()

    def shutdown(self):
        """Cleans up resources."""
        print("Client: Shutting down...")
        self.network_handler.stop()
        pygame.quit()
        print("Client: Shutdown complete.")

if __name__ == "__main__":
    client = GameClient()
    try:
        client.run()
    except Exception as e:
        print(f"An unexpected error occurred in the main client: {e}")
        import traceback
        traceback.print_exc()
        client.shutdown() # Attempt graceful shutdown on error
