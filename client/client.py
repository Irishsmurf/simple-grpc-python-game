import grpc
import threading
import time
import sys
import os
import pygame
from queue import Queue, Empty as QueueEmpty
from collections import deque
import textwrap  # For chat text wrapping

# --- Helper function for PyInstaller ---


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
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
MAX_CHAT_HISTORY = 7
CHAT_INPUT_MAX_LEN = 100
CHAT_DISPLAY_WIDTH = 60  # Approx characters width for wrapping

# --- Attempt to import generated code ---
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
gen_python_path = os.path.join(parent_dir, 'gen', 'python')
if gen_python_path not in sys.path:
    sys.path.insert(0, gen_python_path)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
try:
    from gen.python import game_pb2
    from gen.python import game_pb2_grpc
except ModuleNotFoundError as e:
    print(f"Error importing generated code: {e}")
    sys.exit(1)

# --- Color Palette ---
AVAILABLE_COLORS = [(255, 255, 0), (0, 255, 255), (255, 0, 255),
                    (0, 255, 0), (255, 165, 0), (255, 255, 255)]

# --- Game State Manager ---


class GameStateManager:
    def __init__(self):
        self.state_lock = threading.Lock()
        self.map_lock = threading.Lock()
        self.color_lock = threading.Lock()
        self.latest_game_state = game_pb2.GameState()
        self.players_map = {}
        self.my_player_id = None
        self.connection_error_message = None
        self.world_map_data = None
        self.map_width_tiles = 0
        self.map_height_tiles = 0
        self.world_pixel_width = 0.0
        self.world_pixel_height = 0.0
        self.tile_size = 32
        self.player_colors = {}
        self.next_color_index = 0

    def apply_delta_update(self, delta_update):
        with self.state_lock, self.color_lock:
            for removed_id in delta_update.removed_player_ids:
                if removed_id in self.players_map:
                    del self.players_map[removed_id]
                if removed_id in self.player_colors:
                    del self.player_colors[removed_id]
            for updated_player in delta_update.updated_players:
                player_id = updated_player.id
                self.players_map[player_id] = updated_player
                if player_id not in self.player_colors:
                    self.player_colors[player_id] = AVAILABLE_COLORS[self.next_color_index % len(
                        AVAILABLE_COLORS)]
                    self.next_color_index += 1

    def get_state_snapshot_map(self):
        with self.state_lock:
            return self.players_map

    def set_initial_map_data(self, map_proto):
        print(f"Map: {map_proto.tile_width}x{map_proto.tile_height}")
        temp_map = []
        for y in range(map_proto.tile_height):
            temp_map.append(list(map_proto.rows[y].tiles))
        with self.map_lock:
            self.world_map_data = temp_map
            self.map_width_tiles = map_proto.tile_width
            self.map_height_tiles = map_proto.tile_height
            self.world_pixel_height = map_proto.world_pixel_height
            self.world_pixel_width = map_proto.world_pixel_width
            self.tile_size = map_proto.tile_size_pixels
            print(
                f"World: {self.world_pixel_width}x{self.world_pixel_height}px, Tile: {self.tile_size}px")
        with self.state_lock:
            self.my_player_id = map_proto.assigned_player_id
            print(f"My ID: {self.my_player_id}")

    def get_map_data(self):
        with self.map_lock:
            return self.world_map_data, self.map_width_tiles, self.map_height_tiles, self.tile_size

    def get_world_dimensions(self):
        with self.map_lock:
            return self.world_pixel_width, self.world_pixel_height

    def get_my_player_id(self):
        with self.state_lock:
            return self.my_player_id

    def get_player_color(self, player_id):
        with self.color_lock:
            return self.player_colors.get(player_id, (255, 255, 255))

    def get_all_player_colors(self):
        with self.color_lock:
            return self.player_colors.copy()

    def set_connection_error(self, error_msg):
        with self.state_lock:
            self.connection_error_message = error_msg

    def get_connection_error(self):
        with self.state_lock:
            return self.connection_error_message

# --- Network Handler ---


class NetworkHandler:
    def __init__(self, server_address, state_manager, output_queue):
        self.server_address = server_address
        self.state_manager = state_manager
        self.incoming_queue = output_queue
        self.outgoing_queue = Queue()
        self.input_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.direction_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.stub = None
        self.channel = None
        self._username_to_send = "Player"
        self._stream_started = threading.Event()

    def set_username(
        self, username): self._username_to_send = username if username else "Player"

    def _message_generator(self):
        """Generator yields ClientHello, then messages from outgoing_queue, then PlayerInput."""
        print(
            f"NetHandler: Sending ClientHello for '{self._username_to_send}'")
        hello_msg = game_pb2.ClientHello(
            desired_username=self._username_to_send)
        yield game_pb2.ClientMessage(client_hello=hello_msg)
        print("NetHandler: ClientHello sent.")
        self._stream_started.set()

        while not self.stop_event.is_set():
            outgoing_msg = None
            try:
                retrieved_item = self.outgoing_queue.get_nowait()
                if isinstance(retrieved_item, game_pb2.ClientMessage):
                    outgoing_msg = retrieved_item
                    print(f"NetHandler GEN: Found ClientMessage in outgoing queue!")
                else:
                    print(f"NetHandler GEN: Error - Unexpected item type in outgoing queue: {type(retrieved_item)}")
                    raise QueueEmpty
            except QueueEmpty:
                with self.direction_lock:
                    dir_to_send = self.input_direction
                input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                outgoing_msg = game_pb2.ClientMessage(player_input=input_msg)
            except Exception as e:
                print(f"NetHandler GEN OutQueue Err: Type={type(e).__name__}, Msg='{e}'")
                with self.direction_lock:
                    dir_to_send = self.input_direction
                input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                outgoing_msg = game_pb2.ClientMessage(player_input=input_msg)
            if outgoing_msg:
                msg_type = outgoing_msg.WhichOneof('payload')
                yield outgoing_msg
            else:
                print("NetHandler GEN: Warning - No message prepared to yield this iteration.")
            time.sleep(1.0 / 30.0)

    def _listen_for_updates(self):
        print("NetHandler: Connecting...")
        try:
            stream = self.stub.GameStream(self._message_generator())
            print("NetHandler: Stream started.")
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
            if not self.stop_event.is_set():
                err_msg = f"Conn Err: {e.code()}"
                print(err_msg)
                self.state_manager.set_connection_error(err_msg)
                self.stop_event.set()
        except Exception as e:
            if not self.stop_event.is_set():
                import traceback
                traceback.print_exc()
                err_msg = f"Net Err: {e}"
                print(err_msg)
                self.state_manager.set_connection_error(err_msg)
                self.stop_event.set()
        finally:
            print("NetHandler: Listener finished.")
            self._stream_started.clear()
            self.stop_event.set()

    def send_chat_message(self, text):
        if self._stream_started.is_set() and text:
            chat_req = game_pb2.SendChatMessageRequest(message_text=text)
            client_msg = game_pb2.ClientMessage(send_chat_message=chat_req)
            self.outgoing_queue.put(client_msg)
            print(f"NetHandler: Queued chat: {text[:20]}...")
        elif not text:
            print("NetHandler: Ignoring empty chat.")
        else:
            print("NetHandler: Stream not ready for chat.")

    def start(self):
        print(f"NetHandler: Connecting to {self.server_address}...")
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
            err_msg = f"Timeout connecting"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            return False
        except Exception as e:
            err_msg = f"Conn error: {e}"
            print(err_msg)
            self.state_manager.set_connection_error(err_msg)
            return False

    def stop(self):
        print("NetHandler: Stopping...")
        self.stop_event.set()
        if self.channel:
            print("NetHandler: Closing channel...")
            self.channel.close()
            self.channel = None
        if self.thread and self.thread.is_alive():
            print("NetHandler: Joining thread...")
            self.thread.join(timeout=1.0)
        print("NetHandler: Stopped.")

    def update_input_direction(self, new_direction):
        if self._stream_started.is_set():
            with self.direction_lock:
                if self.input_direction != new_direction:
                    self.input_direction = new_direction

# --- Input Handler (Simplified: Handles movement + quit only) ---


class InputHandler:
    def __init__(self):
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False

    def handle_events_for_movement(self):
        """Processes Pygame events only for movement keys and quit signals."""
        # Called only when chat is NOT active
        self.quit_requested = False  # Reset quit request each frame it's checked
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN

        # Check only relevant events (QUIT, ESC, movement keys)
        # KeyDown for ESC is handled by GameClient now
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_requested = True
                return self.current_direction  # Return last known direction

        # Check pressed keys for movement
        keys_pressed = pygame.key.get_pressed()
        if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]:
            new_direction = game_pb2.PlayerInput.Direction.UP
        elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]:
            new_direction = game_pb2.PlayerInput.Direction.DOWN
        elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]:
            new_direction = game_pb2.PlayerInput.Direction.LEFT
        elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]:
            new_direction = game_pb2.PlayerInput.Direction.RIGHT

        if self.current_direction != new_direction:
            self.current_direction = new_direction

        return self.current_direction

    def check_quit_event(self):
        """Checks only for the QUIT event, separated for clarity."""
        # Call this every frame regardless of chat state
        # More efficient check
        for event in pygame.event.get(eventtype=pygame.QUIT):
            self.quit_requested = True
            return True
        return False

    def should_quit(self): return self.quit_requested


# *** NEW: Chat Manager Class ***
class ChatManager:
    """Handles chat UI state, input, and rendering."""

    def __init__(self, max_history=MAX_CHAT_HISTORY):
        self.active = False
        self.input_text = ""
        self.history = deque(maxlen=max_history)
        self.font = pygame.font.SysFont(None, 22)
        self.input_font = pygame.font.SysFont(
            None, 24)  # Slightly larger for input
        self.text_color = (255, 255, 255)
        self.input_prompt_color = (200, 255, 200)
        self.input_active_color = (255, 255, 255)
        self.input_box_color = (40, 40, 80)  # Background for input box
        # Semi-transparent black for history
        self.history_bg_color = (0, 0, 0, 150)

    def toggle_active(self):
        """Toggles chat input mode."""
        self.active = not self.active
        if self.active:
            self.input_text = ""  # Clear text when activating
            pygame.key.set_repeat(500, 50)  # Enable key repeat for typing
            print("Chat Activated")
        else:
            pygame.key.set_repeat(0, 0)  # Disable key repeat
            print("Chat Deactivated")
        return self.active

    def is_active(self):
        """Returns True if chat input is active."""
        return self.active

    def add_message(self, chat_message_proto):
        """Adds a received ChatMessage proto to the history."""
        self.history.append(chat_message_proto)

    def handle_input_event(self, event):
        """
        Processes a Pygame KEYDOWN event when chat is active.
        Returns the message string to send if Enter was pressed, else None.
        Returns False if chat should be deactivated (e.g. Esc).
        """
        if not self.active or event.type != pygame.KEYDOWN:
            return None  # Should not be called if inactive

        message_to_send = None
        deactivate_chat = False

        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            if self.input_text:
                message_to_send = self.input_text
            self.input_text = ""
            deactivate_chat = True  # Deactivate after sending/attempting
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.input_text = ""
            deactivate_chat = True  # Deactivate on Escape
        elif event.unicode.isprintable():  # Append printable characters
            if len(self.input_text) < CHAT_INPUT_MAX_LEN:
                self.input_text += event.unicode

        if deactivate_chat:
            self.toggle_active()  # Use toggle to handle state change and key repeat

        return message_to_send  # Return the message string or None

    def _render_text_wrapped(self, screen, text, rect, font, color):
        """Helper to render text with basic wrapping."""
        lines = textwrap.wrap(
            text, width=CHAT_DISPLAY_WIDTH)  # Adjust width as needed
        y = rect.top
        line_height = font.get_linesize()
        for line in lines:
            if y + line_height > rect.bottom:  # Stop if exceeding rect height
                break
            try:
                line_surface = font.render(line, True, color)
                screen.blit(line_surface, (rect.left, y))
                y += line_height
            except pygame.error as e:
                print(f"Warn: Render failed for line '{line[:10]}...': {e}")
                y += line_height  # Skip line but advance position

    def draw(self, screen):
        """Draws the chat history and input field."""
        # Draw History (Top Left)
        history_x = 10
        history_y = 10
        line_height = self.font.get_linesize()
        history_height_limit = line_height * \
            MAX_CHAT_HISTORY + 10  # Max height for history
        history_area_rect = pygame.Rect(
            history_x, history_y, SCREEN_WIDTH - 20, history_height_limit)

        # Optional: Draw semi-transparent background for history
        # history_bg_surf = pygame.Surface(history_area_rect.size, pygame.SRCALPHA)
        # history_bg_surf.fill(self.history_bg_color)
        # screen.blit(history_bg_surf, history_area_rect.topleft)

        current_y = history_y
        for msg in self.history:
            prefix = f"{msg.sender_username}: "
            full_text = prefix + msg.message_text
            # Simple wrapping (consider a dedicated text wrapping function for complex needs)
            wrapped_lines = textwrap.wrap(
                full_text, width=CHAT_DISPLAY_WIDTH)  # Adjust width estimate

            for line in wrapped_lines:
                if current_y + line_height > history_y + history_height_limit:
                    break  # Stop if exceeding area
                try:
                    line_surf = self.font.render(line, True, self.text_color)
                    # Small padding
                    screen.blit(line_surf, (history_x + 2, current_y))
                    current_y += line_height
                except pygame.error as e:
                    print(
                        f"Warn: Render failed for chat line '{line[:10]}...': {e}")
                    current_y += line_height  # Skip line
            if current_y > history_y + history_height_limit:
                break

        # Draw Input Field (Bottom Left)
        if self.active:
            prompt = "Say: "
            display_text = prompt + self.input_text
            if time.time() % 1.0 < 0.5:
                display_text += "_"  # Blinking cursor
            input_surf = self.input_font.render(
                display_text, True, self.input_active_color)
            input_rect = input_surf.get_rect(
                left=10, bottom=SCREEN_HEIGHT - 10)
            # Draw background box for input
            bg_rect = input_rect.inflate(10, 6)
            bg_rect.bottom = SCREEN_HEIGHT - 5  # Align bottom
            pygame.draw.rect(screen, self.input_box_color,
                             bg_rect, border_radius=5)
            screen.blit(input_surf, input_rect)
        else:
            # Show toggle hint when inactive
            hint_surf = self.font.render("[T] to chat", True, (150, 150, 150))
            hint_rect = hint_surf.get_rect(left=10, bottom=SCREEN_HEIGHT - 10)
            screen.blit(hint_surf, hint_rect)


# --- Renderer (Simplified - delegates chat drawing) ---
class Renderer:
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")
        pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)
        self.username_font = pygame.font.SysFont(None, 32)
        self.username_color = (230, 230, 230)
        # Chat fonts removed - managed by ChatManager
        self.directional_frames = {}
        self.tile_graphics = {}
        self.player_rect = None
        self.tile_size = 32
        self._load_assets()
        self.camera_x = 0.0
        self.camera_y = 0.0

    def _load_assets(self):
        print("Renderer: Loading assets...")
        try:
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha()
            self.tile_graphics[0] = tileset_img.subsurface(
                (0, 0, self.tile_size, self.tile_size))
            self.tile_graphics[1] = tileset_img.subsurface(
                (self.tile_size, 0, self.tile_size, self.tile_size))
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
            rects = [pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(
                0, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT), pygame.Rect(FRAME_WIDTH, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)]
            states = [game_pb2.AnimationState.RUNNING_UP, game_pb2.AnimationState.RUNNING_DOWN,
                      game_pb2.AnimationState.RUNNING_LEFT, game_pb2.AnimationState.RUNNING_RIGHT]
            for state, rect in zip(states, rects):
                self.directional_frames[state] = sheet_img.subsurface(rect)
            self.directional_frames[game_pb2.AnimationState.IDLE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]
            self.directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = self.directional_frames[game_pb2.AnimationState.RUNNING_DOWN]
            self.player_rect = self.directional_frames[game_pb2.AnimationState.IDLE].get_rect(
            )
            print(f"Renderer: Assets loaded.")
        except pygame.error as e:
            print(f"Renderer: Error loading assets: {e}")
            raise

    def update_camera(self, target_x, target_y, world_width, world_height):
        target_cam_x = target_x-self.screen_width/2
        target_cam_y = target_y-self.screen_height/2
        if world_width > self.screen_width:
            self.camera_x = max(
                0.0, min(target_cam_x, world_width-self.screen_width))
        else:
            self.camera_x = (world_width-self.screen_width)/2
        if world_height > self.screen_height:
            self.camera_y = max(
                0.0, min(target_cam_y, world_height-self.screen_height))
        else:
            self.camera_y = (world_height-self.screen_height)/2

    def draw_map(self, map_data, map_w, map_h, tile_size):
        if not map_data or tile_size <= 0:
            return
        if self.tile_size != tile_size:
            self.tile_size = tile_size
        buffer = 1
        stx = max(0, int(self.camera_x/self.tile_size)-buffer)
        etx = min(map_w, int(
            (self.camera_x+self.screen_width)/self.tile_size)+buffer+1)
        sty = max(0, int(self.camera_y/self.tile_size)-buffer)
        ety = min(map_h, int(
            (self.camera_y+self.screen_height)/self.tile_size)+buffer+1)
        for y in range(sty, ety):
            if y >= len(map_data):
                continue
            for x in range(stx, etx):
                if x >= len(map_data[y]):
                    continue
                tid = map_data[y][x]
                if tid in self.tile_graphics:
                    self.screen.blit(
                        self.tile_graphics[tid], (x*self.tile_size-self.camera_x, y*self.tile_size-self.camera_y))

    def draw_players(self, player_map, player_colors, my_player_id):
        if not player_map or not self.player_rect:
            return
        for pid, player in player_map.items():
            state = player.current_animation_state
            surf = self.directional_frames.get(
                state, self.directional_frames[game_pb2.AnimationState.IDLE])
            if surf:
                sx = player.x_pos-self.camera_x
                sy = player.y_pos-self.camera_y
                prect = surf.get_rect(center=(int(sx), int(sy)))
                tsurf = surf.copy()
                color = player_colors.get(pid, (255, 255, 255))
                tisurf = pygame.Surface(prect.size, pygame.SRCALPHA)
                tisurf.fill(color+(128,))
                tsurf.blit(tisurf, (0, 0),
                           special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(tsurf, prect)
                if player.username:
                    usurf = self.username_font.render(
                        player.username, True, self.username_color)
                    urect = usurf.get_rect(
                        centerx=prect.centerx, bottom=prect.top-2)
                    self.screen.blit(usurf, urect)
                if pid == my_player_id:
                    pygame.draw.rect(
                        self.screen, (255, 255, 255), prect.inflate(4, 4), 2)

    def draw_error_message(self, message):
        surf = self.error_font.render(message, True, self.error_text_color)
        rect = surf.get_rect(
            center=(self.screen_width//2, self.screen_height//2))
        self.screen.blit(surf, rect)

    # *** CHANGED: Render only draws game world, no chat ***
    def render_game_world(self, state_manager):
        """Renders only the map and players."""
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
            return False  # Indicate error state
        else:
            current_player_map = state_manager.get_state_snapshot_map()
            map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id()
            player_colors = state_manager.get_all_player_colors()

            my_player_snapshot = current_player_map.get(my_player_id)
            if my_player_snapshot:
                world_w, world_h = state_manager.get_world_dimensions()
                self.update_camera(my_player_snapshot.x_pos,
                                   my_player_snapshot.y_pos, world_w, world_h)

            self.screen.fill(BACKGROUND_COLOR)
            self.draw_map(map_data, map_w, map_h, tile_size)
            self.draw_players(current_player_map, player_colors, my_player_id)
            return True  # Indicate success


# --- Game Client (Uses ChatManager) ---
class GameClient:
    def __init__(self):
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.input_handler = InputHandler()  # Simplified input handler
        # *** NEW: Instantiate ChatManager ***
        self.chat_manager = ChatManager()
        self.clock = pygame.time.Clock()
        self.server_message_queue = Queue()
        self.network_handler = NetworkHandler(
            SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False
        self.username = ""

    def get_username_input(self):
        input_active = True
        input_text = ""
        prompt_font = pygame.font.SysFont(None, 40)
        input_font = pygame.font.SysFont(None, 35)
        prompt_surf = prompt_font.render(
            "Enter Username:", True, (200, 200, 255))
        prompt_rect = prompt_surf.get_rect(
            center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2-50))
        instr_surf = input_font.render(
            "(Press Enter to join)", True, (150, 150, 150))
        instr_rect = instr_surf.get_rect(
            center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2+50))
        while input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if input_text:
                            input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif len(input_text) < 16:
                        if event.unicode.isalnum() or event.unicode in ['_', '-']:
                            input_text += event.unicode
            self.renderer.screen.fill(BACKGROUND_COLOR)
            self.renderer.screen.blit(prompt_surf, prompt_rect)
            self.renderer.screen.blit(instr_surf, instr_rect)
            input_surf = input_font.render(input_text, True, (255, 255, 255))
            input_rect = input_surf.get_rect(
                center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
            pygame.draw.rect(self.renderer.screen,
                             (50, 50, 100), input_rect.inflate(20, 10))
            self.renderer.screen.blit(input_surf, input_rect)
            pygame.display.flip()
            self.clock.tick(30)
        return input_text

    # *** CHANGED: Pass chat messages to ChatManager ***
    def _process_server_messages(self):
        try:
            while True:
                message_type, message_data = self.server_message_queue.get_nowait()
                if message_type == "map_data":
                    self.state_manager.set_initial_map_data(message_data)
                    _, _, _, tile_size = self.state_manager.get_map_data()
                    if self.renderer.tile_size != tile_size:
                        self.renderer.tile_size = tile_size
                elif message_type == "delta_update":
                    self.state_manager.apply_delta_update(message_data)
                elif message_type == "chat":
                    self.chat_manager.add_message(
                        message_data)  # Add to chat history
                else:
                    print(f"Warn: Unknown queue msg type: {message_type}")
        except QueueEmpty:
            pass
        except Exception as e:
            print(f"Error processing queue: {e}")

    def run(self):
        self.username = self.get_username_input()
        if self.username is None:
            self.shutdown()
            return
        print(f"Username: {self.username}")
        self.network_handler.set_username(self.username)

        self.running = True
        if not self.network_handler.start():
            print("Failed network start.")
            self.running = False
            while True:  # Error display
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        pygame.quit()
                        return
                # Pass dummy chat state to renderer during error display
                self.renderer.render_game_world(self.state_manager)
                # Draw chat UI even on error screen? Maybe not.
                self.chat_manager.draw(self.renderer.screen)
                pygame.display.flip()
                self.clock.tick(10)

        print("Waiting for player ID...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:  # Wait loop
            self._process_server_messages()
            if self.network_handler.stop_event.is_set():
                print("Net stopped waiting for ID.")
                self.running = False
                break
            if time.time() - wait_start_time > 10:
                print("Timeout waiting for ID.")
                self.state_manager.set_connection_error(
                    "Timeout waiting for ID.")
                self.running = False
                break
            time.sleep(0.05)

        print("Starting main loop...")
        current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        while self.running:
            if self.network_handler.stop_event.is_set():
                print("Stop event.")
                self.running = False
                continue

            # --- Input Handling Refactored ---
            message_to_send = None
            # 1. Check for global quit events first
            if self.input_handler.check_quit_event():
                self.running = False
                continue

            # 2. Process other events (Keyboard)
            for event in pygame.event.get():  # Process other events like KEYDOWN
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        break  # Handle ESC globally
                    elif event.key == pygame.K_t and not self.chat_manager.is_active():
                        self.chat_manager.toggle_active()
                    elif self.chat_manager.is_active():
                        # Pass event to chat manager if active
                        message_to_send = self.chat_manager.handle_input_event(
                            event)
                # Handle other event types if needed

            if not self.running:
                continue  # Check if ESC quit

            # 3. Handle Movement Input (if chat not active)
            if not self.chat_manager.is_active():
                current_direction = self.input_handler.handle_events_for_movement()
                self.network_handler.update_input_direction(current_direction)
                if self.input_handler.should_quit():  # Check if QUIT event was caught by movement handler
                    self.running = False
                    continue
            else:
                # Ensure player stops when chat is active
                self.network_handler.update_input_direction(
                    game_pb2.PlayerInput.Direction.UNKNOWN)

            # 4. Send Chat Message if ready
            if message_to_send:
                self.network_handler.send_chat_message(message_to_send)
            # --- End Input Handling ---

            # Process incoming messages
            self._process_server_messages()

            # --- Rendering Refactored ---
            # 1. Render the game world
            render_ok = self.renderer.render_game_world(self.state_manager)

            # 2. Render the chat UI on top (only if game world render was ok)
            if render_ok:
                self.chat_manager.draw(self.renderer.screen)

            # 3. Update the display
            pygame.display.flip()
            # --- End Rendering ---

            self.clock.tick(FPS)

        print("Client: Exiting loop.")
        self.shutdown()

    def shutdown(self):
        print("Client: Shutting down...")
        self.network_handler.stop()
        pygame.quit()
        print("Client: Shutdown complete.")


if __name__ == "__main__":
    client = GameClient()
    try:
        client.run()
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        try:
            client.shutdown()
        except Exception as se:
            print(f"Shutdown error: {se}")
