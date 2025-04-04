import grpc
import threading
import time
import sys
import os
import pygame
from queue import Queue, Empty as QueueEmpty

# --- Helper function for PyInstaller ---
def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

# --- Configuration ---
SERVER_ADDRESS = "192.168.41.108:50051" # Needs to match server
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50)
FPS = 60
SPRITE_SHEET_PATH = resource_path("assets/player_sheet_256.png")
TILESET_PATH = resource_path("assets/tileset.png")
FRAME_WIDTH = 128
FRAME_HEIGHT = 128

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
    print(f"Error importing generated code: {e}"); sys.exit(1)

# --- Color Palette ---
AVAILABLE_COLORS = [ (255, 255, 0), (0, 255, 255), (255, 0, 255), (0, 255, 0), (255, 165, 0), (255, 255, 255) ]

# --- Game State Manager ---
class GameStateManager: # ... (implementation remains the same as client_py_delta) ...
    def __init__(self):
        self.state_lock = threading.Lock(); self.map_lock = threading.Lock(); self.color_lock = threading.Lock()
        self.latest_game_state = game_pb2.GameState(); self.players_map = {}
        self.my_player_id = None; self.connection_error_message = None
        self.world_map_data = None; self.map_width_tiles = 0; self.map_height_tiles = 0
        self.world_pixel_width = 0.0; self.world_pixel_height = 0.0; self.tile_size = 32
        self.player_colors = {}; self.next_color_index = 0
    def apply_delta_update(self, delta_update):
        with self.state_lock:
            with self.color_lock:
                for removed_id in delta_update.removed_player_ids:
                    if removed_id in self.players_map: del self.players_map[removed_id]
                    if removed_id in self.player_colors: del self.player_colors[removed_id]
                for updated_player in delta_update.updated_players:
                    player_id = updated_player.id
                    self.players_map[player_id] = updated_player # Add/Update player data (includes username now)
                    if player_id not in self.player_colors:
                        self.player_colors[player_id] = AVAILABLE_COLORS[self.next_color_index % len(AVAILABLE_COLORS)]
                        self.next_color_index += 1
    def get_state_snapshot_map(self):
        with self.state_lock: return self.players_map # Return reference
    def set_initial_map_data(self, map_proto):
        print(f"Map: {map_proto.tile_width}x{map_proto.tile_height}"); temp_map = []
        for y in range(map_proto.tile_height): temp_map.append(list(map_proto.rows[y].tiles))
        with self.map_lock:
            self.world_map_data = temp_map; self.map_width_tiles = map_proto.tile_width; self.map_height_tiles = map_proto.tile_height
            self.world_pixel_height = map_proto.world_pixel_height; self.world_pixel_width = map_proto.world_pixel_width; self.tile_size = map_proto.tile_size_pixels
            print(f"World: {self.world_pixel_width}x{self.world_pixel_height}px, Tile: {self.tile_size}px")
        with self.state_lock: self.my_player_id = map_proto.assigned_player_id; print(f"My ID: {self.my_player_id}")
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

# --- Network Handler (Sends ClientHello first) ---
class NetworkHandler:
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
        self._username_to_send = "Player" # Placeholder, set before starting thread
        self._stream_started = threading.Event() # To signal when stream is ready for input

    # *** NEW: Method to set username before starting ***
    def set_username(self, username):
        self._username_to_send = username if username else "Player" # Ensure not empty

    def _message_generator(self):
        """Generator function to send client messages (Hello first, then Input)."""
        # 1. Send ClientHello
        print(f"NetworkHandler: Sending ClientHello for user '{self._username_to_send}'")
        hello_msg = game_pb2.ClientHello(desired_username=self._username_to_send)
        yield game_pb2.ClientMessage(client_hello=hello_msg)
        print("NetworkHandler: ClientHello sent.")
        self._stream_started.set() # Signal that the stream is ready for PlayerInput

        # 2. Send PlayerInput messages continuously
        while not self.stop_event.is_set():
            with self.direction_lock:
                dir_to_send = self.input_direction
            # Wrap PlayerInput in ClientMessage
            input_msg = game_pb2.PlayerInput(direction=dir_to_send)
            yield game_pb2.ClientMessage(player_input=input_msg)
            time.sleep(1.0 / 30.0) # ~30 inputs per second

    def _listen_for_updates(self):
        """The main loop for the network thread."""
        print("NetworkHandler: Connecting to stream...")
        try:
            # *** CHANGE: Use _message_generator which sends Hello first ***
            stream = self.stub.GameStream(self._message_generator())
            print("NetworkHandler: Stream started. Waiting for server messages...")

            for message in stream: # Process incoming ServerMessages
                if self.stop_event.is_set(): break
                if message.HasField("initial_map_data"):
                    self.output_queue.put(("map_data", message.initial_map_data))
                elif message.HasField("delta_update"):
                     self.output_queue.put(("delta_update", message.delta_update))

        except grpc.RpcError as e: # ... (error handling unchanged) ...
            if not self.stop_event.is_set(): error_msg = f"Conn Error: {e.code()} - {e.details()}"; print(f"NetHandler Error: {error_msg}"); self.state_manager.set_connection_error(error_msg); self.stop_event.set()
            else: print("NetHandler: Shutdown (gRPC Err)")
        except Exception as e: # ... (error handling unchanged) ...
             if not self.stop_event.is_set(): import traceback; traceback.print_exc(); error_msg = f"Unexpected Net Err: {e}"; print(error_msg); self.state_manager.set_connection_error(error_msg); self.stop_event.set()
             else: print("NetHandler: Shutdown (Exc)")
        finally:
            print("NetworkHandler: Listener loop finished.")
            self._stream_started.clear() # Clear signal on exit
            self.stop_event.set()

    def start(self): # ... (start logic unchanged) ...
        print(f"NetworkHandler: Connecting to {self.server_address}...")
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("NetworkHandler: Channel connected.")
            self.stub = game_pb2_grpc.GameServiceStub(self.channel)
            self.stop_event.clear(); self._stream_started.clear() # Clear events
            self.thread = threading.Thread(target=self._listen_for_updates, daemon=True)
            self.thread.start()
            print("NetworkHandler: Listener thread started.")
            return True
        except grpc.FutureTimeoutError: err_msg = f"Timeout connecting to {self.server_address}"; print(err_msg); self.state_manager.set_connection_error(err_msg); return False
        except Exception as e: err_msg = f"Connection error: {e}"; print(err_msg); self.state_manager.set_connection_error(err_msg); return False # Catch potential channel close errors too

    def stop(self): # ... (stop logic unchanged) ...
        print("NetworkHandler: Stopping..."); self.stop_event.set()
        if self.channel: print("NetHandler: Closing channel..."); self.channel.close(); self.channel = None
        if self.thread and self.thread.is_alive(): print("NetHandler: Joining thread..."); self.thread.join(timeout=1.0);
        print("NetworkHandler: Stopped.")

    def update_input_direction(self, new_direction):
        # Only update if the stream has been started (ClientHello sent)
        if self._stream_started.is_set():
            with self.direction_lock:
                if self.input_direction != new_direction:
                    self.input_direction = new_direction


# --- Renderer (Adds username rendering) ---
class Renderer:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width; self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")
        pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)
        # *** ADDED: Font for usernames ***
        self.username_font = pygame.font.SysFont(None, 20) # Smaller font
        self.username_color = (230, 230, 230) # Light grey/white

        self.directional_frames = {}; self.tile_graphics = {}
        self.player_rect = None; self.tile_size = 32
        self._load_assets()
        self.camera_x = 0.0; self.camera_y = 0.0

    def _load_assets(self): # ... (unchanged) ...
        print("Renderer: Loading assets...")
        try:
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha(); print(f"Renderer: Loaded tileset from {TILESET_PATH}")
            self.tile_graphics[0] = tileset_img.subsurface((0, 0, self.tile_size, self.tile_size)); self.tile_graphics[1] = tileset_img.subsurface((self.tile_size, 0, self.tile_size, self.tile_size))
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha(); print(f"Renderer: Loaded sprite sheet from {SPRITE_SHEET_PATH}")
            rects = [pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(0, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)] # up, down, left, right
            states = [game_pb2.AnimationState.RUNNING_UP, game_pb2.AnimationState.RUNNING_DOWN, game_pb2.AnimationState.RUNNING_LEFT, game_pb2.AnimationState.RUNNING_RIGHT]
            for state, rect in zip(states, rects): self.directional_frames[state] = sheet_img.subsurface(rect)
            self.directional_frames[game_pb2.AnimationState.IDLE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]; self.directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]
            self.player_rect = self.directional_frames[game_pb2.AnimationState.IDLE].get_rect(); print(f"Renderer: Assets loaded.")
        except pygame.error as e: print(f"Renderer: Error loading assets: {e}"); raise

    def update_camera(self, target_x, target_y, world_width, world_height): # ... (unchanged) ...
        target_cam_x = target_x - self.screen_width / 2; target_cam_y = target_y - self.screen_height / 2
        if world_width > self.screen_width: self.camera_x = max(0.0, min(target_cam_x, world_width - self.screen_width))
        else: self.camera_x = (world_width - self.screen_width) / 2
        if world_height > self.screen_height: self.camera_y = max(0.0, min(target_cam_y, world_height - self.screen_height))
        else: self.camera_y = (world_height - self.screen_height) / 2

    def draw_map(self, map_data, map_w, map_h, tile_size): # ... (unchanged) ...
        if not map_data or tile_size <= 0: return
        if self.tile_size != tile_size: self.tile_size = tile_size # TODO: Re-extract graphics if needed
        buffer = 1; start_tile_x = max(0, int(self.camera_x / self.tile_size) - buffer); end_tile_x = min(map_w, int((self.camera_x + self.screen_width) / self.tile_size) + buffer + 1); start_tile_y = max(0, int(self.camera_y / self.tile_size) - buffer); end_tile_y = min(map_h, int((self.camera_y + self.screen_height) / self.tile_size) + buffer + 1)
        for y in range(start_tile_y, end_tile_y):
            if y >= len(map_data): continue
            for x in range(start_tile_x, end_tile_x):
                if x >= len(map_data[y]): continue
                tile_id = map_data[y][x];
                if tile_id in self.tile_graphics: self.screen.blit(self.tile_graphics[tile_id], (x * self.tile_size - self.camera_x, y * self.tile_size - self.camera_y))

    def draw_players(self, player_map, player_colors, my_player_id):
        """Draws the players and their usernames."""
        if not player_map or not self.player_rect: return

        for player_id, player in player_map.items():
            player_state = player.current_animation_state
            current_frame_surface = self.directional_frames.get(player_state, self.directional_frames[game_pb2.AnimationState.IDLE])

            if current_frame_surface:
                screen_x = player.x_pos - self.camera_x
                screen_y = player.y_pos - self.camera_y
                player_rect = current_frame_surface.get_rect(center=(int(screen_x), int(screen_y)))

                # Tinting
                temp_sprite_frame = current_frame_surface.copy()
                color = player_colors.get(player.id, (255, 255, 255))
                tint_surface = pygame.Surface(player_rect.size, pygame.SRCALPHA); tint_surface.fill(color + (128,))
                temp_sprite_frame.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                # Draw player sprite
                self.screen.blit(temp_sprite_frame, player_rect)

                # *** ADDED: Draw username ***
                if player.username: # Check if username exists
                    username_surface = self.username_font.render(player.username, True, self.username_color)
                    username_rect = username_surface.get_rect(centerx=player_rect.centerx, bottom=player_rect.top - 2) # Position above sprite
                    self.screen.blit(username_surface, username_rect)

                # Indicator for own player
                if player.id == my_player_id:
                    pygame.draw.rect(self.screen, (255, 255, 255), player_rect.inflate(4, 4), 2)

    def draw_error_message(self, message): # ... (unchanged) ...
        error_surface = self.error_font.render(message, True, self.error_text_color); error_rect = error_surface.get_rect(center=(self.screen_width // 2, self.screen_height // 2)); self.screen.blit(error_surface, error_rect)

    def render(self, state_manager): # ... (unchanged) ...
        error_msg = state_manager.get_connection_error()
        if error_msg: self.screen.fill(BACKGROUND_COLOR); self.draw_error_message(error_msg)
        else:
            current_player_map = state_manager.get_state_snapshot_map(); map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id(); player_colors = state_manager.get_all_player_colors()
            my_player_snapshot = current_player_map.get(my_player_id)
            if my_player_snapshot: world_w, world_h = state_manager.get_world_dimensions(); self.update_camera(my_player_snapshot.x_pos, my_player_snapshot.y_pos, world_w, world_h)
            self.screen.fill(BACKGROUND_COLOR); self.draw_map(map_data, map_w, map_h, tile_size); self.draw_players(current_player_map, player_colors, my_player_id)
        pygame.display.flip()

# --- Input Handler ---
class InputHandler: # ... (no changes needed) ...
    def __init__(self): self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN; self.quit_requested = False
    def handle_events(self):
        self.quit_requested = False; new_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.quit_requested = True; return self.current_direction
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.quit_requested = True; return self.current_direction
        keys_pressed = pygame.key.get_pressed()
        if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]: new_direction = game_pb2.PlayerInput.Direction.UP
        elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]: new_direction = game_pb2.PlayerInput.Direction.DOWN
        elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]: new_direction = game_pb2.PlayerInput.Direction.LEFT
        elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]: new_direction = game_pb2.PlayerInput.Direction.RIGHT
        if self.current_direction != new_direction: self.current_direction = new_direction
        return self.current_direction
    def should_quit(self): return self.quit_requested


# --- Game Client (Adds username input screen) ---
class GameClient:
    def __init__(self):
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT) # Renderer now has username font
        self.input_handler = InputHandler()
        self.clock = pygame.time.Clock()
        self.server_message_queue = Queue()
        self.network_handler = NetworkHandler(SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False
        self.username = ""

    # *** NEW: Simple UI loop to get username ***
    def get_username_input(self):
        """Displays a simple screen to input username."""
        input_active = True
        input_text = ""
        prompt_font = pygame.font.SysFont(None, 40)
        input_font = pygame.font.SysFont(None, 35)
        prompt_surf = prompt_font.render("Enter Username:", True, (200, 200, 255))
        prompt_rect = prompt_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
        instr_surf = input_font.render("(Press Enter to join)", True, (150, 150, 150))
        instr_rect = instr_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50))

        while input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None # Indicate quit
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if input_text: # Require some text
                            input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif len(input_text) < 16: # Limit username length
                        # Allow alphanumeric and maybe underscore/dash
                        if event.unicode.isalnum() or event.unicode in ['_', '-']:
                             input_text += event.unicode

            self.renderer.screen.fill(BACKGROUND_COLOR)
            self.renderer.screen.blit(prompt_surf, prompt_rect)
            self.renderer.screen.blit(instr_surf, instr_rect)

            # Render current input text
            input_surf = input_font.render(input_text, True, (255, 255, 255))
            input_rect = input_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            pygame.draw.rect(self.renderer.screen, (50, 50, 100), input_rect.inflate(20, 10)) # Input box background
            self.renderer.screen.blit(input_surf, input_rect)

            pygame.display.flip()
            self.clock.tick(30) # Lower FPS for input screen

        return input_text

    def _process_server_messages(self): # ... (implementation remains the same as client_py_delta) ...
        try:
            while True:
                message_type, message_data = self.server_message_queue.get_nowait()
                if message_type == "map_data": self.state_manager.set_initial_map_data(message_data); _, _, _, ts = self.state_manager.get_map_data(); self.renderer.tile_size = ts
                elif message_type == "delta_update": self.state_manager.apply_delta_update(message_data)
                else: print(f"Warn: Unknown queue msg type: {message_type}")
        except QueueEmpty: pass
        except Exception as e: print(f"Error processing queue: {e}")

    def run(self):
        """Main game loop."""
        # *** CHANGE: Get username first ***
        self.username = self.get_username_input()
        if self.username is None: # User quit during input
            print("Client: Quit during username input.")
            self.shutdown(); return

        print(f"Client: Username entered: {self.username}")
        self.network_handler.set_username(self.username) # Pass username to network handler

        # --- Start Network and Main Loop ---
        self.running = True
        if not self.network_handler.start():
            print("Failed to start network handler. Exiting.")
            self.running = False
            # Error display loop (unchanged)
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE): pygame.quit(); return
                self.renderer.render(self.state_manager); self.clock.tick(10)

        # Wait briefly for player ID (unchanged)
        print("Waiting for player ID from server...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:
            self._process_server_messages()
            if self.network_handler.stop_event.is_set(): print("Net thread stopped waiting for ID."); self.running = False; break
            if time.time() - wait_start_time > 10: print("Timeout waiting for ID."); self.state_manager.set_connection_error("Timeout waiting for player ID."); self.running = False; break
            time.sleep(0.05)

        print("Starting main game loop...")
        while self.running: # Main loop (unchanged)
            if self.network_handler.stop_event.is_set(): print("Stop event detected."); self.running = False; continue
            current_direction = self.input_handler.handle_events()
            if self.input_handler.should_quit(): self.running = False; continue
            self.network_handler.update_input_direction(current_direction)
            self._process_server_messages()
            self.renderer.render(self.state_manager)
            self.clock.tick(FPS)

        print("Client: Exiting main loop.")
        self.shutdown()

    def shutdown(self): # ... (unchanged) ...
        print("Client: Shutting down..."); self.network_handler.stop(); pygame.quit(); print("Client: Shutdown complete.")

if __name__ == "__main__":
    client = GameClient()
    try: client.run()
    except Exception as e:
        print(f"An unexpected error occurred: {e}"); import traceback; traceback.print_exc()
        try: client.shutdown()
        except Exception as shutdown_e: print(f"Error during shutdown: {shutdown_e}")
