import grpc
import threading
import time
import sys
import os
import pygame
from queue import Queue, Empty as QueueEmpty
from collections import deque # For chat history

# --- Helper function for PyInstaller ---
def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

# --- Configuration ---
SERVER_ADDRESS = "192.168.41.108:50051"
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50)
FPS = 60
SPRITE_SHEET_PATH = resource_path("assets/player_sheet_256.png")
TILESET_PATH = resource_path("assets/tileset.png")
FRAME_WIDTH = 128
FRAME_HEIGHT = 128
MAX_CHAT_HISTORY = 7 # Number of chat lines to display

# --- Attempt to import generated code ---
# (Ensure paths are correct for your setup)
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
class GameStateManager: # ... (No changes needed from previous username version) ...
    def __init__(self):
        self.state_lock=threading.Lock(); self.map_lock=threading.Lock(); self.color_lock=threading.Lock()
        self.latest_game_state=game_pb2.GameState(); self.players_map={}
        self.my_player_id=None; self.connection_error_message=None
        self.world_map_data=None; self.map_width_tiles=0; self.map_height_tiles=0
        self.world_pixel_width=0.0; self.world_pixel_height=0.0; self.tile_size=32
        self.player_colors={}; self.next_color_index=0
    def apply_delta_update(self, delta_update):
        with self.state_lock, self.color_lock: # Combine locks if safe
            for removed_id in delta_update.removed_player_ids:
                if removed_id in self.players_map: del self.players_map[removed_id]
                if removed_id in self.player_colors: del self.player_colors[removed_id]
            for updated_player in delta_update.updated_players:
                player_id = updated_player.id; self.players_map[player_id] = updated_player
                if player_id not in self.player_colors: self.player_colors[player_id] = AVAILABLE_COLORS[self.next_color_index % len(AVAILABLE_COLORS)]; self.next_color_index += 1
    def get_state_snapshot_map(self):
        with self.state_lock: return self.players_map
    def set_initial_map_data(self, map_proto):
        print(f"Map: {map_proto.tile_width}x{map_proto.tile_height}"); temp_map=[]
        for y in range(map_proto.tile_height): temp_map.append(list(map_proto.rows[y].tiles))
        with self.map_lock: self.world_map_data=temp_map; self.map_width_tiles=map_proto.tile_width; self.map_height_tiles=map_proto.tile_height; self.world_pixel_height=map_proto.world_pixel_height; self.world_pixel_width=map_proto.world_pixel_width; self.tile_size=map_proto.tile_size_pixels; print(f"World: {self.world_pixel_width}x{self.world_pixel_height}px, Tile: {self.tile_size}px")
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

# --- Network Handler (Adds outgoing queue for chat) ---
class NetworkHandler:
    def __init__(self, server_address, state_manager, output_queue):
        self.server_address = server_address
        self.state_manager = state_manager
        self.incoming_queue = output_queue # Renamed for clarity
        self.outgoing_queue = Queue() # *** NEW: Queue for outgoing messages (like chat) ***
        self.input_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.direction_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.stub = None
        self.channel = None
        self._username_to_send = "Player"
        self._stream_started = threading.Event()

    def set_username(self, username):
        self._username_to_send = username if username else "Player"

    # *** CHANGED: Message generator checks outgoing queue first ***
    def _message_generator(self):
        """Generator yields ClientHello, then messages from outgoing_queue, then PlayerInput."""
        # 1. Send ClientHello
        print(f"NetHandler: Sending ClientHello for '{self._username_to_send}'")
        hello_msg = game_pb2.ClientHello(desired_username=self._username_to_send)
        yield game_pb2.ClientMessage(client_hello=hello_msg)
        print("NetHandler: ClientHello sent.")
        self._stream_started.set()

        # 2. Send other messages (Chat first, then Input)
        while not self.stop_event.is_set():
            outgoing_msg = None
            try:
                # Check for priority messages (like chat) first, non-blocking
                outgoing_msg = self.outgoing_queue.get_nowait()
                print("NetHandler: Sending message from outgoing queue.")
            except QueueEmpty:
                # No priority message, send current player input
                with self.direction_lock:
                    dir_to_send = self.input_direction
                input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                outgoing_msg = game_pb2.ClientMessage(player_input=input_msg)
            except Exception as e:
                 print(f"NetHandler: Error getting from outgoing queue: {e}")
                 # Fallback to sending input if queue fails unexpectedly
                 with self.direction_lock: dir_to_send = self.input_direction
                 input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                 outgoing_msg = game_pb2.ClientMessage(player_input=input_msg)


            if outgoing_msg:
                 yield outgoing_msg

            # Small sleep to prevent busy-waiting and control input send rate
            time.sleep(1.0 / 30.0)

    def _listen_for_updates(self):
        print("NetHandler: Connecting...")
        try:
            stream = self.stub.GameStream(self._message_generator())
            print("NetHandler: Stream started.")
            for message in stream:
                if self.stop_event.is_set(): break
                # *** CHANGE: Check for chat_message ***
                if message.HasField("initial_map_data"):
                    self.incoming_queue.put(("map_data", message.initial_map_data))
                elif message.HasField("delta_update"):
                     self.incoming_queue.put(("delta_update", message.delta_update))
                elif message.HasField("chat_message"):
                     self.incoming_queue.put(("chat", message.chat_message)) # Put chat on queue
                # else: Ignore unknown server message types

        except grpc.RpcError as e: # ... (error handling unchanged) ...
            if not self.stop_event.is_set(): error_msg=f"Conn Err: {e.code()}"; print(error_msg); self.state_manager.set_connection_error(error_msg); self.stop_event.set()
        except Exception as e: # ... (error handling unchanged) ...
             if not self.stop_event.is_set(): import traceback; traceback.print_exc(); error_msg=f"Net Err: {e}"; print(error_msg); self.state_manager.set_connection_error(error_msg); self.stop_event.set()
        finally:
            print("NetHandler: Listener finished."); self._stream_started.clear(); self.stop_event.set()

    # *** NEW: Method to send chat message via the outgoing queue ***
    def send_chat_message(self, text):
        if self._stream_started.is_set() and text:
            chat_req = game_pb2.SendChatMessageRequest(message_text=text)
            client_msg = game_pb2.ClientMessage(send_chat_message=chat_req)
            self.outgoing_queue.put(client_msg)
            print(f"NetHandler: Queued chat message: {text}")
        elif not text:
            print("NetHandler: Ignoring empty chat message.")
        else:
             print("NetHandler: Cannot send chat, stream not ready.")


    def start(self):
        print(f"NetHandler: Connecting to {self.server_address}...")
        try:
            self.channel = grpc.insecure_channel(self.server_address); grpc.channel_ready_future(self.channel).result(timeout=5); print("NetHandler: Channel connected.")
            self.stub = game_pb2_grpc.GameServiceStub(self.channel); self.stop_event.clear(); self._stream_started.clear()
            self.thread = threading.Thread(target=self._listen_for_updates, daemon=True); self.thread.start(); print("NetHandler: Listener thread started.")
            return True
        except grpc.FutureTimeoutError: err_msg=f"Timeout connecting"; print(err_msg); self.state_manager.set_connection_error(err_msg); return False
        except Exception as e: err_msg=f"Conn error: {e}"; print(err_msg); self.state_manager.set_connection_error(err_msg); return False
    def stop(self):
        print("NetHandler: Stopping..."); self.stop_event.set()
        if self.channel: print("NetHandler: Closing channel..."); self.channel.close(); self.channel = None
        if self.thread and self.thread.is_alive(): print("NetHandler: Joining thread..."); self.thread.join(timeout=1.0);
        print("NetHandler: Stopped.")
    def update_input_direction(self, new_direction):
        if self._stream_started.is_set():
            with self.direction_lock:
                if self.input_direction != new_direction: self.input_direction = new_direction

# --- Renderer (Adds chat display) ---
class Renderer:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width; self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client"); pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26); self.error_text_color = (255, 100, 100)
        self.username_font = pygame.font.SysFont(None, 20); self.username_color = (230, 230, 230)
        # *** ADDED: Font for chat display ***
        self.chat_font = pygame.font.SysFont(None, 22) # Slightly larger than username
        self.chat_color = (255, 255, 255) # White for chat text
        self.chat_input_color = (200, 255, 200) # Light green for input prompt

        self.directional_frames = {}; self.tile_graphics = {}
        self.player_rect = None; self.tile_size = 32
        self._load_assets(); self.camera_x = 0.0; self.camera_y = 0.0

    def _load_assets(self):
        print("Renderer: Loading assets...")
        try:
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha(); self.tile_graphics[0] = tileset_img.subsurface((0, 0, self.tile_size, self.tile_size)); self.tile_graphics[1] = tileset_img.subsurface((self.tile_size, 0, self.tile_size, self.tile_size))
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
            rects = [pygame.Rect(0,0,FRAME_WIDTH,FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH,0,FRAME_WIDTH,FRAME_HEIGHT), pygame.Rect(0,FRAME_HEIGHT,FRAME_WIDTH,FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH,FRAME_HEIGHT,FRAME_WIDTH,FRAME_HEIGHT)]
            states = [game_pb2.AnimationState.RUNNING_UP, game_pb2.AnimationState.RUNNING_DOWN, game_pb2.AnimationState.RUNNING_LEFT, game_pb2.AnimationState.RUNNING_RIGHT]
            for state, rect in zip(states, rects): self.directional_frames[state] = sheet_img.subsurface(rect)
            self.directional_frames[game_pb2.AnimationState.IDLE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]; self.directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]
            self.player_rect = self.directional_frames[game_pb2.AnimationState.IDLE].get_rect(); print(f"Renderer: Assets loaded.")
        except pygame.error as e: print(f"Renderer: Error loading assets: {e}"); raise

    def update_camera(self, target_x, target_y, world_width, world_height):
        target_cam_x=target_x-self.screen_width/2; target_cam_y=target_y-self.screen_height/2
        if world_width > self.screen_width: self.camera_x=max(0.0, min(target_cam_x, world_width-self.screen_width))
        else: self.camera_x=(world_width-self.screen_width)/2
        if world_height > self.screen_height: self.camera_y=max(0.0, min(target_cam_y, world_height-self.screen_height))
        else: self.camera_y=(world_height-self.screen_height)/2

    def draw_map(self, map_data, map_w, map_h, tile_size):
        if not map_data or tile_size <= 0: return
        if self.tile_size != tile_size: self.tile_size = tile_size
        buffer=1; start_tile_x=max(0,int(self.camera_x/self.tile_size)-buffer); end_tile_x=min(map_w,int((self.camera_x+self.screen_width)/self.tile_size)+buffer+1); start_tile_y=max(0,int(self.camera_y/self.tile_size)-buffer); end_tile_y=min(map_h,int((self.camera_y+self.screen_height)/self.tile_size)+buffer+1)
        for y in range(start_tile_y, end_tile_y):
            if y >= len(map_data): continue
            for x in range(start_tile_x, end_tile_x):
                if x >= len(map_data[y]): continue
                tile_id=map_data[y][x];
                if tile_id in self.tile_graphics: self.screen.blit(self.tile_graphics[tile_id], (x*self.tile_size-self.camera_x, y*self.tile_size-self.camera_y))

    def draw_players(self, player_map, player_colors, my_player_id):
        if not player_map or not self.player_rect: return
        for player_id, player in player_map.items():
            player_state=player.current_animation_state; current_frame_surface=self.directional_frames.get(player_state, self.directional_frames[game_pb2.AnimationState.IDLE])
            if current_frame_surface:
                screen_x=player.x_pos-self.camera_x; screen_y=player.y_pos-self.camera_y; player_rect=current_frame_surface.get_rect(center=(int(screen_x), int(screen_y)))
                temp_sprite_frame=current_frame_surface.copy(); color=player_colors.get(player.id, (255,255,255)); tint_surface=pygame.Surface(player_rect.size, pygame.SRCALPHA); tint_surface.fill(color+(128,)); temp_sprite_frame.blit(tint_surface, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(temp_sprite_frame, player_rect)
                if player.username: username_surface=self.username_font.render(player.username, True, self.username_color); username_rect=username_surface.get_rect(centerx=player_rect.centerx, bottom=player_rect.top-2); self.screen.blit(username_surface, username_rect)
                if player.id == my_player_id: pygame.draw.rect(self.screen, (255,255,255), player_rect.inflate(4,4), 2)

    def draw_error_message(self, message):
        surf=self.error_font.render(message, True, self.error_text_color); rect=surf.get_rect(center=(self.screen_width//2, self.screen_height//2)); self.screen.blit(surf, rect)

    # *** NEW: Draw chat history ***
    def draw_chat_history(self, chat_history):
        y_offset = 10 # Starting Y position for chat
        line_height = self.chat_font.get_linesize()
        for msg in chat_history: # deque iterates oldest to newest
            text = f"{msg.sender_username}: {msg.message_text}"
            try:
                chat_surf = self.chat_font.render(text, True, self.chat_color)
                chat_rect = chat_surf.get_rect(left=10, top=y_offset)
                # Optional: Add background rect for readability
                # bg_rect = chat_rect.inflate(4, 2)
                # pygame.draw.rect(self.screen, (0, 0, 0, 150), bg_rect) # Semi-transparent black
                self.screen.blit(chat_surf, chat_rect)
                y_offset += line_height
            except pygame.error as e:
                 print(f"Warning: Could not render chat text '{text[:20]}...': {e}") # Log error if rendering fails (e.g., unsupported chars in font)


    # *** NEW: Draw chat input prompt ***
    def draw_chat_input(self, input_text, is_active):
        prompt = "Say: " if is_active else "[T] to chat"
        full_text = prompt + input_text
        if is_active and (time.time() % 1.0 < 0.5): # Blinking cursor
             full_text += "_"

        input_surf = self.chat_font.render(full_text, True, self.chat_input_color)
        input_rect = input_surf.get_rect(left=10, bottom=self.screen_height - 10)
        self.screen.blit(input_surf, input_rect)

    # *** CHANGED: Render calls chat drawing methods ***
    def render(self, state_manager, chat_history, chat_input_text, chat_active):
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
        else:
            current_player_map = state_manager.get_state_snapshot_map()
            map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id()
            player_colors = state_manager.get_all_player_colors()

            my_player_snapshot = current_player_map.get(my_player_id)
            if my_player_snapshot:
                 world_w, world_h = state_manager.get_world_dimensions()
                 self.update_camera(my_player_snapshot.x_pos, my_player_snapshot.y_pos, world_w, world_h)

            self.screen.fill(BACKGROUND_COLOR)
            self.draw_map(map_data, map_w, map_h, tile_size)
            self.draw_players(current_player_map, player_colors, my_player_id)
            # *** ADDED: Draw chat ***
            self.draw_chat_history(chat_history)
            self.draw_chat_input(chat_input_text, chat_active)

        pygame.display.flip()

# --- Input Handler (Modified to handle chat toggle/input) ---
class InputHandler:
    def __init__(self):
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False
        self.chat_toggle_pressed = False # Detect T press edge
        self.chat_send_pressed = False # Detect Enter press edge
        self.chat_backspace_pressed = False # Detect Backspace press edge
        self.typed_char = None # Character typed this frame

    def handle_events(self, chat_active):
        """Processes Pygame events, handles movement OR chat input."""
        self.quit_requested = False
        self.chat_toggle_pressed = False
        self.chat_send_pressed = False
        self.chat_backspace_pressed = False
        self.typed_char = None
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_requested = True
                return self.current_direction # Exit event loop
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.quit_requested = True
                    return self.current_direction # Exit event loop

                # Handle chat mode toggle (T key)
                if event.key == pygame.K_t and not chat_active: # Only toggle on if not already active
                    self.chat_toggle_pressed = True
                    # Don't process movement keys if toggling chat on
                    continue # Skip further processing for this key press

                # Handle input within chat mode
                if chat_active:
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        self.chat_send_pressed = True
                    elif event.key == pygame.K_BACKSPACE:
                        self.chat_backspace_pressed = True
                    else:
                        # Store the typed character (handles unicode)
                        if event.unicode.isprintable(): # Basic check
                             self.typed_char = event.unicode
                    # Prevent movement keys while typing in chat
                    continue # Skip movement check below

                # Handle movement keys (only if NOT in chat mode)
                # (This part is now skipped if chat_active is True)
                # No change needed here, handled by the 'continue' above

        # Check pressed keys for movement (only if NOT in chat mode)
        if not chat_active:
            keys_pressed = pygame.key.get_pressed()
            if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]: new_direction = game_pb2.PlayerInput.Direction.UP
            elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]: new_direction = game_pb2.PlayerInput.Direction.DOWN
            elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]: new_direction = game_pb2.PlayerInput.Direction.LEFT
            elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]: new_direction = game_pb2.PlayerInput.Direction.RIGHT

            if self.current_direction != new_direction:
                self.current_direction = new_direction

        return self.current_direction # Return movement direction

    def should_quit(self): return self.quit_requested
    def did_toggle_chat(self): return self.chat_toggle_pressed
    def did_send_chat(self): return self.chat_send_pressed
    def did_press_backspace(self): return self.chat_backspace_pressed
    def get_typed_char(self): return self.typed_char


# --- Game Client (Adds chat state and logic) ---
class GameClient:
    def __init__(self):
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.input_handler = InputHandler()
        self.clock = pygame.time.Clock()
        self.server_message_queue = Queue()
        self.network_handler = NetworkHandler(SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False
        self.username = ""
        # *** NEW: Chat state ***
        self.chat_active = False # Is the user currently typing a chat message?
        self.chat_input_text = "" # The message being typed
        self.chat_history = deque(maxlen=MAX_CHAT_HISTORY) # Store recent ChatMessage protos

    def get_username_input(self):
        input_active=True; input_text=""; prompt_font=pygame.font.SysFont(None, 40); input_font=pygame.font.SysFont(None, 35)
        prompt_surf=prompt_font.render("Enter Username:", True, (200,200,255)); prompt_rect=prompt_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2-50))
        instr_surf=input_font.render("(Press Enter to join)", True, (150,150,150)); instr_rect=instr_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2+50))
        while input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if input_text: input_active = False
                    elif event.key == pygame.K_BACKSPACE: input_text = input_text[:-1]
                    elif len(input_text) < 16:
                        if event.unicode.isalnum() or event.unicode in ['_', '-']: input_text += event.unicode
            self.renderer.screen.fill(BACKGROUND_COLOR); self.renderer.screen.blit(prompt_surf, prompt_rect); self.renderer.screen.blit(instr_surf, instr_rect)
            input_surf=input_font.render(input_text, True, (255,255,255)); input_rect=input_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2)); pygame.draw.rect(self.renderer.screen, (50,50,100), input_rect.inflate(20,10)); self.renderer.screen.blit(input_surf, input_rect)
            pygame.display.flip(); self.clock.tick(30)
        return input_text

    # *** CHANGED: Process server messages handles chat ***
    def _process_server_messages(self):
        try:
            while True:
                message_type, message_data = self.server_message_queue.get_nowait()
                if message_type == "map_data":
                    self.state_manager.set_initial_map_data(message_data)
                    _, _, _, tile_size = self.state_manager.get_map_data()
                    if self.renderer.tile_size != tile_size: self.renderer.tile_size = tile_size
                elif message_type == "delta_update":
                    self.state_manager.apply_delta_update(message_data)
                # *** ADDED: Handle incoming chat messages ***
                elif message_type == "chat":
                    print(f"Chat Received: {message_data.sender_username}: {message_data.message_text}")
                    self.chat_history.append(message_data) # Add to deque
                else:
                     print(f"Warn: Unknown queue msg type: {message_type}")
        except QueueEmpty: pass
        except Exception as e: print(f"Error processing queue: {e}")

    def run(self):
        self.username = self.get_username_input()
        if self.username is None: self.shutdown(); return
        print(f"Username: {self.username}")
        self.network_handler.set_username(self.username)

        self.running = True
        if not self.network_handler.start():
            print("Failed network start."); self.running = False
            while True: # Error display
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE): pygame.quit(); return
                self.renderer.render(self.state_manager, self.chat_history, self.chat_input_text, self.chat_active); self.clock.tick(10) # Pass chat state

        print("Waiting for player ID..."); wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running: # Wait loop
            self._process_server_messages()
            if self.network_handler.stop_event.is_set(): print("Net stopped waiting for ID."); self.running = False; break
            if time.time() - wait_start_time > 10: print("Timeout waiting for ID."); self.state_manager.set_connection_error("Timeout waiting for ID."); self.running = False; break
            time.sleep(0.05)

        print("Starting main loop...")
        while self.running:
            if self.network_handler.stop_event.is_set(): print("Stop event."); self.running = False; continue

            # Handle Input (handles chat toggle/typing)
            current_direction = self.input_handler.handle_events(self.chat_active)
            if self.input_handler.should_quit(): self.running = False; continue

            # *** ADDED: Chat input logic ***
            if self.input_handler.did_toggle_chat():
                self.chat_active = True
                self.chat_input_text = "" # Clear input on activation
                print("Chat activated")
            elif self.chat_active:
                 # Process typing within chat mode
                 typed_char = self.input_handler.get_typed_char()
                 if typed_char:
                      # Add character (limit length)
                      if len(self.chat_input_text) < 100: # Limit message length
                           self.chat_input_text += typed_char
                 elif self.input_handler.did_press_backspace():
                      self.chat_input_text = self.chat_input_text[:-1]
                 elif self.input_handler.did_send_chat():
                      # Send the message
                      if self.chat_input_text:
                           self.network_handler.send_chat_message(self.chat_input_text)
                      # Deactivate chat input
                      self.chat_input_text = ""
                      self.chat_active = False
                      print("Chat deactivated")
                 elif self.input_handler.should_quit() or (self.input_handler.did_toggle_chat()): # Allow Esc/T again to cancel chat
                     self.chat_input_text = ""
                     self.chat_active = False
                     print("Chat cancelled")


            # Update network handler with movement (only if not chatting)
            if not self.chat_active:
                self.network_handler.update_input_direction(current_direction)
            else: # Ensure player stops moving when chat is active
                 self.network_handler.update_input_direction(game_pb2.PlayerInput.Direction.UNKNOWN)


            # Process incoming messages (state deltas, chat)
            self._process_server_messages()

            # Render game state and chat UI
            self.renderer.render(self.state_manager, self.chat_history, self.chat_input_text, self.chat_active)

            self.clock.tick(FPS)

        print("Client: Exiting loop.")
        self.shutdown()

    def shutdown(self):
        print("Client: Shutting down..."); self.network_handler.stop(); pygame.quit(); print("Client: Shutdown complete.")

if __name__ == "__main__":
    client = GameClient()
    try: client.run()
    except Exception as e:
        print(f"Unexpected error: {e}"); import traceback; traceback.print_exc()
        try: client.shutdown()
        except Exception as se: print(f"Shutdown error: {se}")

