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
SERVER_ADDRESS = "192.168.41.108:50051" # Needs to match server flag or default
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50)
FRAME_WIDTH = 128
FRAME_HEIGHT = 128
FPS = 60

TILESET_PATH = resource_path("assets/tileset.png")
SPRITE_SHEET_PATH = resource_path("assets/player_sheet_256.png")

# --- Attempt to import generated code ---
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
gen_python_path = os.path.join(parent_dir, 'gen', 'python')
if gen_python_path not in sys.path: sys.path.insert(0, gen_python_path)
if parent_dir not in sys.path: sys.path.insert(0, parent_dir)

try:
    from gen.python import game_pb2
    from gen.python import game_pb2_grpc
except ModuleNotFoundError as e:
    print(f"Error importing generated code: {e}")
    print("sys.path:", sys.path)
    print("Ensure 'protoc' was run correctly and 'gen/python' exists.")
    sys.exit(1)

# --- Color Palette ---
AVAILABLE_COLORS = [ (255, 255, 0), (0, 255, 255), (255, 0, 255), (0, 255, 0), (255, 165, 0), (255, 255, 255) ]

# --- Game State Manager (Handles Delta Updates) ---
class GameStateManager:
    """Manages the client-side game state by applying delta updates."""
    def __init__(self):
        self.state_lock = threading.Lock()
        self.map_lock = threading.Lock()
        self.color_lock = threading.Lock()

        # *** CHANGE: Initialize with an empty GameState proto ***
        self.latest_game_state = game_pb2.GameState()
        self.players_map = {} # Use a map for efficient updates/deletes

        self.my_player_id = None
        self.connection_error_message = None

        # Map data
        self.world_map_data = None
        self.map_width_tiles = 0
        self.map_height_tiles = 0
        self.world_pixel_width = 0.0
        self.world_pixel_height = 0.0
        self.tile_size = 32

        # Player appearance
        self.player_colors = {}
        self.next_color_index = 0

    # *** REMOVED: update_state (replaced by apply_delta_update) ***
    # def update_state(self, new_state): ...

    # *** NEW: Method to apply delta updates ***
    def apply_delta_update(self, delta_update):
        """Applies changes from a DeltaUpdate message to the local state."""
        with self.state_lock:
            # Process removed players
            with self.color_lock: # Lock colors while removing
                for removed_id in delta_update.removed_player_ids:
                    if removed_id in self.players_map:
                        del self.players_map[removed_id]
                        print(f"Player {removed_id} removed.")
                    if removed_id in self.player_colors:
                        del self.player_colors[removed_id]

            # Process updated/added players
            with self.color_lock: # Lock colors while potentially adding
                for updated_player in delta_update.updated_players:
                    player_id = updated_player.id
                    # Add or update player in the map
                    self.players_map[player_id] = updated_player
                    # Assign color if new
                    if player_id not in self.player_colors:
                        self.player_colors[player_id] = AVAILABLE_COLORS[self.next_color_index % len(AVAILABLE_COLORS)]
                        self.next_color_index += 1
                        print(f"Player {player_id} added/updated.")

            # *** OPTIONAL: Update the GameState protobuf list if needed elsewhere ***
            # This rebuilds the list from the map, potentially slow if frequent.
            # Only do this if other parts of the code *require* the GameState.players list format.
            # self.latest_game_state.ClearField("players") # Clear existing list
            # self.latest_game_state.players.extend(self.players_map.values())


    def get_state_snapshot_map(self):
        """Returns a *reference* to the internal players map. Use with caution or copy."""
        with self.state_lock:
             # Returning a direct reference for performance. Renderer needs to handle this.
             # If Renderer needs a list, it should build it from this map.
            return self.players_map

    # --- Other methods remain largely the same ---
    def set_initial_map_data(self, map_proto):
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
        with self.state_lock:
            self.my_player_id = map_proto.assigned_player_id
            print(f"*** Received own player ID: {self.my_player_id} ***")

    def get_map_data(self):
        with self.map_lock: return self.world_map_data, self.map_width_tiles, self.map_height_tiles, self.tile_size
    def get_world_dimensions(self):
        with self.map_lock: return self.world_pixel_width, self.world_pixel_height
    def get_my_player_id(self):
        with self.state_lock: return self.my_player_id
    def get_player_color(self, player_id):
        with self.color_lock: return self.player_colors.get(player_id, (255, 255, 255))
    def get_all_player_colors(self):
        with self.color_lock: return self.player_colors.copy()
    def set_connection_error(self, error_msg):
        with self.state_lock: self.connection_error_message = error_msg
    def get_connection_error(self):
        with self.state_lock: return self.connection_error_message


# --- Network Handler (Minor change to put specific message types) ---
class NetworkHandler:
    """Handles gRPC communication in a separate thread."""
    def __init__(self, server_address, state_manager, output_queue):
        self.server_address = server_address
        self.state_manager = state_manager
        self.output_queue = output_queue
        self.input_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.direction_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.stub = None
        self.channel = None

    def _input_generator(self):
        while not self.stop_event.is_set():
            with self.direction_lock: dir_to_send = self.input_direction
            yield game_pb2.PlayerInput(direction=dir_to_send)
            time.sleep(1.0 / 30.0)

    def _listen_for_updates(self):
        """The main loop for the network thread."""
        print("NetworkHandler: Connecting to stream...")
        try:
            stream = self.stub.GameStream(self._input_generator())
            print("NetworkHandler: Stream started. Waiting for server messages...")

            for message in stream:
                if self.stop_event.is_set(): break
                # *** CHANGE: Put specific message content onto queue ***
                if message.HasField("initial_map_data"):
                    self.output_queue.put(("map_data", message.initial_map_data))
                elif message.HasField("delta_update"):
                     self.output_queue.put(("delta_update", message.delta_update))
                # else: Ignore unknown message types?

        except grpc.RpcError as e: # ... (error handling unchanged) ...
            if not self.stop_event.is_set():
                error_msg = f"Connection Error: {e.code()} - {e.details()}. Try restarting Client/Server."
                print(f"NetworkHandler: Error receiving game state: {e.code()} - {e.details()}")
                self.state_manager.set_connection_error(error_msg)
                self.stop_event.set()
            else: print("NetworkHandler: Shutting down due to stop event (gRPC Cancel/Error)")
        except Exception as e: # ... (error handling unchanged) ...
             if not self.stop_event.is_set():
                import traceback
                traceback.print_exc()
                print(f"NetworkHandler: Unexpected error: {e}")
                self.state_manager.set_connection_error(f"Unexpected Network Error: {e}")
                self.stop_event.set()
             else: print("NetworkHandler: Shutting down due to stop event (Exception).")
        finally:
            print("NetworkHandler: Listener loop finished.")
            self.stop_event.set()

    def start(self):
        print(f"NetworkHandler: Attempting to connect to {self.server_address}...")
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("NetworkHandler: Channel connected.")
            self.stub = game_pb2_grpc.GameServiceStub(self.channel)
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._listen_for_updates, daemon=True)
            self.thread.start()
            print("NetworkHandler: Listener thread started.")
            return True
        except grpc.FutureTimeoutError:
            err_msg = f"Error: Connection timed out after 5 seconds. Is the server running at {self.server_address}?"
            print(err_msg); self.state_manager.set_connection_error(err_msg)
            if self.channel: self.channel.close()
            return False
        except grpc.RpcError as e:
            err_msg = f"gRPC error during connection: {e.code()} - {e.details()}"
            print(err_msg); self.state_manager.set_connection_error(err_msg)
            if self.channel: self.channel.close()
            return False
        except Exception as e:
            err_msg = f"Unexpected error during connection: {e}"
            print(err_msg); self.state_manager.set_connection_error(err_msg)
            if self.channel: self.channel.close()
            return False

    def stop(self):
        print("NetworkHandler: Stopping...")
        self.stop_event.set()
        if self.channel:
            print("NetworkHandler: Closing gRPC channel...")
            self.channel.close()
            self.channel = None
        if self.thread and self.thread.is_alive():
            print("NetworkHandler: Waiting for listener thread to finish...")
            self.thread.join(timeout=1.0)
            if self.thread.is_alive(): print("NetworkHandler: Warning - Listener thread did not exit cleanly.")
        print("NetworkHandler: Stopped.")

    def update_input_direction(self, new_direction):
        with self.direction_lock:
            if self.input_direction != new_direction: self.input_direction = new_direction


# --- Renderer (Minor change to iterate over player map) ---
class Renderer:
    """Handles Pygame rendering and asset loading."""
    def __init__(self, screen_width, screen_height): # ... (init unchanged) ...
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")
        pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)
        self.directional_frames = {}
        self.tile_graphics = {}
        self.player_rect = None
        self.tile_size = 32
        self._load_assets()
        self.camera_x = 0.0
        self.camera_y = 0.0

    def _load_assets(self): # ... (load assets unchanged) ...
        print("Renderer: Loading assets...")
        try:
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha()
            print(f"Renderer: Loaded tileset from {TILESET_PATH}")
            self.tile_graphics[0] = tileset_img.subsurface((0, 0, self.tile_size, self.tile_size))
            self.tile_graphics[1] = tileset_img.subsurface((self.tile_size, 0, self.tile_size, self.tile_size))
            print(f"Renderer: Loaded {len(self.tile_graphics)} initial tile graphics (size {self.tile_size}x{self.tile_size}).")
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
            print(f"Renderer: Loaded sprite sheet from {SPRITE_SHEET_PATH}")
            up_rect = pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT)
            down_rect = pygame.Rect(FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT)
            left_rect = pygame.Rect(0, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
            right_rect = pygame.Rect(FRAME_WIDTH, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
            self.directional_frames[game_pb2.AnimationState.RUNNING_UP] = sheet_img.subsurface(up_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN] = sheet_img.subsurface(down_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_LEFT] = sheet_img.subsurface(left_rect)
            self.directional_frames[game_pb2.AnimationState.RUNNING_RIGHT] = sheet_img.subsurface(right_rect)
            self.directional_frames[game_pb2.AnimationState.IDLE] = sheet_img.subsurface(down_rect)
            self.directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = sheet_img.subsurface(down_rect)
            print(f"Renderer: Extracted {len(self.directional_frames)} directional frames.")
            self.player_rect = self.directional_frames[game_pb2.AnimationState.IDLE].get_rect()
        except pygame.error as e:
            print(f"Renderer: Error loading assets: {e}")
            raise

    def update_camera(self, target_x, target_y, world_width, world_height): # ... (unchanged) ...
        target_cam_x = target_x - self.screen_width / 2
        target_cam_y = target_y - self.screen_height / 2
        if world_width > self.screen_width: self.camera_x = max(0.0, min(target_cam_x, world_width - self.screen_width))
        else: self.camera_x = (world_width - self.screen_width) / 2
        if world_height > self.screen_height: self.camera_y = max(0.0, min(target_cam_y, world_height - self.screen_height))
        else: self.camera_y = (world_height - self.screen_height) / 2

    def draw_map(self, map_data, map_w, map_h, tile_size): # ... (unchanged) ...
        if not map_data or tile_size <= 0: return
        if self.tile_size != tile_size:
             print(f"Renderer: Tile size changed to {tile_size}.")
             self.tile_size = tile_size
             # TODO: Re-extract tile graphics if needed.
        buffer = 1
        start_tile_x = max(0, int(self.camera_x / self.tile_size) - buffer)
        end_tile_x = min(map_w, int((self.camera_x + self.screen_width) / self.tile_size) + buffer + 1)
        start_tile_y = max(0, int(self.camera_y / self.tile_size) - buffer)
        end_tile_y = min(map_h, int((self.camera_y + self.screen_height) / self.tile_size) + buffer + 1)
        for y in range(start_tile_y, end_tile_y):
            if y >= len(map_data): continue
            for x in range(start_tile_x, end_tile_x):
                if x >= len(map_data[y]): continue
                tile_id = map_data[y][x]
                if tile_id in self.tile_graphics:
                    tile_surface = self.tile_graphics[tile_id]
                    screen_x = x * self.tile_size - self.camera_x
                    screen_y = y * self.tile_size - self.camera_y
                    self.screen.blit(tile_surface, (screen_x, screen_y))

    # *** CHANGE: Takes player_map instead of game_state ***
    def draw_players(self, player_map, player_colors, my_player_id):
        """Draws the players from the player map."""
        if not player_map or not self.player_rect:
            return

        # Iterate through the map directly
        for player_id, player in player_map.items():
            player_state = player.current_animation_state
            current_frame_surface = self.directional_frames.get(player_state, self.directional_frames[game_pb2.AnimationState.IDLE])

            if current_frame_surface:
                screen_x = player.x_pos - self.camera_x
                screen_y = player.y_pos - self.camera_y
                player_rect = current_frame_surface.get_rect()
                player_rect.center = (int(screen_x), int(screen_y))

                # Tinting
                temp_sprite_frame = current_frame_surface.copy()
                color = player_colors.get(player.id, (255, 255, 255))
                tint_surface = pygame.Surface(player_rect.size, pygame.SRCALPHA)
                tint_surface.fill(color + (128,))
                temp_sprite_frame.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                # Indicator for own player
                if player.id == my_player_id:
                    pygame.draw.rect(self.screen, (255, 255, 255), player_rect.inflate(4, 4), 2)

                self.screen.blit(temp_sprite_frame, player_rect)

    def draw_error_message(self, message): # ... (unchanged) ...
        error_surface = self.error_font.render(message, True, self.error_text_color)
        error_rect = error_surface.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
        self.screen.blit(error_surface, error_rect)

    def render(self, state_manager):
        """Main render loop."""
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
        else:
            # *** CHANGE: Get player map instead of full GameState proto ***
            current_player_map = state_manager.get_state_snapshot_map()
            map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id()
            player_colors = state_manager.get_all_player_colors()

            # Update camera based on own player's position (if available)
            my_player_snapshot = current_player_map.get(my_player_id)
            if my_player_snapshot:
                 world_w, world_h = state_manager.get_world_dimensions()
                 self.update_camera(my_player_snapshot.x_pos, my_player_snapshot.y_pos, world_w, world_h)

            # --- Drawing ---
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_map(map_data, map_w, map_h, tile_size)
            # *** CHANGE: Pass player map to draw_players ***
            self.draw_players(current_player_map, player_colors, my_player_id)

        pygame.display.flip()

# --- Input Handler ---
class InputHandler: # ... (no changes needed) ...
    def __init__(self):
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False
    def handle_events(self):
        self.quit_requested = False
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.quit_requested = True; return self.current_direction # Return current dir on quit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.quit_requested = True; return self.current_direction # Return current dir on quit
        keys_pressed = pygame.key.get_pressed()
        if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]: new_direction = game_pb2.PlayerInput.Direction.UP
        elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]: new_direction = game_pb2.PlayerInput.Direction.DOWN
        elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]: new_direction = game_pb2.PlayerInput.Direction.LEFT
        elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]: new_direction = game_pb2.PlayerInput.Direction.RIGHT
        if self.current_direction != new_direction: self.current_direction = new_direction
        return self.current_direction
    def should_quit(self): return self.quit_requested


# --- Game Client (Processes delta updates) ---
class GameClient:
    """Main game client class."""
    def __init__(self): # ... (init unchanged) ...
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.input_handler = InputHandler()
        self.clock = pygame.time.Clock()
        self.server_message_queue = Queue()
        self.network_handler = NetworkHandler(SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False

    def _process_server_messages(self):
        """Processes messages received from the network thread."""
        try:
            while True:
                message_type, message_data = self.server_message_queue.get_nowait()

                # *** CHANGE: Handle different message types ***
                if message_type == "map_data":
                    self.state_manager.set_initial_map_data(message_data)
                    _, _, _, tile_size = self.state_manager.get_map_data()
                    if self.renderer.tile_size != tile_size:
                         print(f"Client: Updating renderer tile size to {tile_size}")
                         self.renderer.tile_size = tile_size
                elif message_type == "delta_update":
                    self.state_manager.apply_delta_update(message_data)
                else:
                     print(f"Warning: Received unknown message type from queue: {message_type}")

        except QueueEmpty:
            pass # No more messages for now
        except Exception as e:
            print(f"Error processing server message queue: {e}")


    def run(self): # ... (run loop structure largely unchanged) ...
        self.running = True
        if not self.network_handler.start():
            print("Failed to start network handler. Exiting.")
            self.running = False
            while True: # Error display loop
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        pygame.quit(); return
                self.renderer.render(self.state_manager)
                self.clock.tick(10)

        print("Waiting for player ID from server...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:
            self._process_server_messages()
            if self.network_handler.stop_event.is_set():
                 print("Network thread stopped while waiting for player ID. Exiting.")
                 self.running = False; break
            if time.time() - wait_start_time > 10:
                 print("Error: Timed out waiting for player ID from server.")
                 self.state_manager.set_connection_error("Timed out waiting for player ID.")
                 self.running = False; break
            time.sleep(0.05)

        print("Starting main game loop...")
        while self.running:
            if self.network_handler.stop_event.is_set():
                print("Stop event detected from network thread. Exiting loop.")
                self.running = False; continue

            current_direction = self.input_handler.handle_events()
            if self.input_handler.should_quit():
                self.running = False; continue

            self.network_handler.update_input_direction(current_direction)
            self._process_server_messages() # Apply deltas received
            self.renderer.render(self.state_manager) # Render based on updated state
            self.clock.tick(FPS)

        print("Client: Exiting main loop.")
        self.shutdown()

    def shutdown(self): # ... (shutdown unchanged) ...
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
        client.shutdown()

