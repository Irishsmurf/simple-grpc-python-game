import grpc
import threading
import time
import sys
import os
import pygame
from queue import Queue, Empty as QueueEmpty
from collections import deque
import textwrap
import hashlib  # For username color hashing

# --- Helper function for PyInstaller ---


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
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
# Assumes font is in client/fonts/
FONT_PATH = resource_path("fonts/DejaVuSansMono.ttf")
FRAME_WIDTH = 128
FRAME_HEIGHT = 128
MAX_CHAT_HISTORY = 7
CHAT_INPUT_MAX_LEN = 100
CHAT_DISPLAY_WIDTH = 70

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
# Chat Colors
CHAT_TIMESTAMP_COLOR = (150, 150, 150)
CHAT_DEFAULT_USERNAME_COLOR = (210, 210, 210)
CHAT_MY_MESSAGE_COLOR = (220, 220, 100)
CHAT_OTHER_MESSAGE_COLOR = (255, 255, 255)
CHAT_INPUT_PROMPT_COLOR = (200, 255, 200)
CHAT_INPUT_ACTIVE_COLOR = (255, 255, 255)
CHAT_INPUT_BOX_COLOR_ACTIVE = (50, 50, 100)
CHAT_INPUT_BOX_COLOR_INACTIVE = (30, 30, 60)
CHAT_INPUT_BORDER_COLOR_ACTIVE = (150, 150, 255)
CHAT_HISTORY_BG_COLOR = (0, 0, 0, 150)  # Semi-transparent black


# --- Game State Manager ---
class GameStateManager:  # ... (No changes needed) ...
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


class NetworkHandler:  # ... (No changes needed) ...
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
        print(
            f"NetHandler GEN: Sending ClientHello for '{self._username_to_send}'")
        hello_msg = game_pb2.ClientHello(
            desired_username=self._username_to_send)
        yield game_pb2.ClientMessage(client_hello=hello_msg)
        print("NetHandler GEN: ClientHello sent.")
        self._stream_started.set()
        while not self.stop_event.is_set():
            outgoing_msg_to_yield = None
            try:
                retrieved_item = self.outgoing_queue.get_nowait()
                if isinstance(retrieved_item, game_pb2.ClientMessage):
                    outgoing_msg_to_yield = retrieved_item
                    print(f"NetHandler GEN: Found ClientMessage in outgoing queue!")
                else:
                    print(
                        f"NetHandler GEN: Error - Unexpected item type: {type(retrieved_item)}")
                    raise QueueEmpty
            except QueueEmpty:
                with self.direction_lock:
                    dir_to_send = self.input_direction
                input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                outgoing_msg_to_yield = game_pb2.ClientMessage(
                    player_input=input_msg)
            except Exception as e:
                print(
                    f"NetHandler GEN OutQueue Err: Type={type(e).__name__}, Msg='{e}'")
                with self.direction_lock:
                    dir_to_send = self.input_direction
                    input_msg = game_pb2.PlayerInput(direction=dir_to_send)
                    outgoing_msg_to_yield = game_pb2.ClientMessage(
                        player_input=input_msg)
            if outgoing_msg_to_yield:
                msg_type = outgoing_msg_to_yield.WhichOneof('payload')
                yield outgoing_msg_to_yield
            else:
                print("NetHandler GEN: Warning - No message to yield.")
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
            print(f"NetHandler SEND: Putting chat: '{text[:30]}...'")
            self.outgoing_queue.put(client_msg)
            print(
                f"NetHandler SEND: OutQueue size: {self.outgoing_queue.qsize()}")
        elif not text:
            print("NetHandler SEND: Ignoring empty chat.")
        else:
            print("NetHandler SEND: Stream not ready.")

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

# --- Input Handler (Simplified) ---


class InputHandler:  # ... (unchanged) ...
    def __init__(self): 
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False

    def handle_events_for_movement(self):
        self.quit_requested = False
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        pygame.event.pump()
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
        for event in pygame.event.get(eventtype=pygame.QUIT):
            self.quit_requested = True
            return True
        return False

    def should_quit(self): return self.quit_requested


# --- Chat Manager Class (Draw BG Added) ---
class ChatManager:
    """Handles chat UI state, input, and rendering with UI polish."""

    def __init__(self, max_history=MAX_CHAT_HISTORY):
        self.active = False
        self.input_text = ""
        self.history = deque(maxlen=max_history)
        self.my_username = ""
        try:
            self.font = pygame.font.Font(FONT_PATH, 14)
            self.input_font = pygame.font.Font(FONT_PATH, 16)
            print(f"ChatManager: Loaded font '{FONT_PATH}'")
        except pygame.error as e:
            print(
                f"Warning: Could not load font '{FONT_PATH}'. Using default SysFont. Error: {e}")
            self.font = pygame.font.SysFont(None, 22)
            self.input_font = pygame.font.SysFont(None, 24)
        # Colors defined globally

    # ... (unchanged) ...
    def set_my_username(self, username): self.my_username = username

    def _get_color_for_username(self, username):  # ... (unchanged) ...
        if not username:
            return CHAT_DEFAULT_USERNAME_COLOR
        hasher = hashlib.sha1(username.encode('utf-8'))
        hash_bytes = hasher.digest()
        r = 100 + (hash_bytes[0] % 156)
        g = 100 + (hash_bytes[1] % 156)
        b = 100 + (hash_bytes[2] % 156)
        return (r, g, b)

    def toggle_active(self):  # ... (unchanged) ...
        self.active = not self.active
        if self.active:
            self.input_text = ""
            pygame.key.set_repeat(500, 50)
            print("Chat Activated")
        else:
            pygame.key.set_repeat(0, 0)
            print("Chat Deactivated")
        return self.active

    def is_active(self): return self.active  # ... (unchanged) ...

    def add_message(self, chat_message_proto):  # ... (unchanged) ...
        timestamp = time.time()
        self.history.append(
            (timestamp, chat_message_proto.sender_username, chat_message_proto.message_text))

    def handle_input_event(self, event):  # ... (unchanged) ...
        if not self.active or event.type != pygame.KEYDOWN:
            return None
        message_to_send = None
        deactivate_chat = False
        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            if self.input_text:
                message_to_send = self.input_text
            self.input_text = ""
            deactivate_chat = True
        elif event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.key == pygame.K_ESCAPE:
            self.input_text = ""
            deactivate_chat = True
        elif event.unicode.isprintable():
            if len(self.input_text) < CHAT_INPUT_MAX_LEN:
                self.input_text += event.unicode
        if deactivate_chat:
            self.toggle_active()
        return message_to_send

    # ... (unchanged helper) ...
    def _render_text_wrapped(self, screen, text, rect, font, color):
        lines = textwrap.wrap(text, width=CHAT_DISPLAY_WIDTH,
                              replace_whitespace=False, drop_whitespace=False)
        y = rect.top
        line_height = font.get_linesize()
        for line in lines:
            if y + line_height > rect.bottom:
                break
            try:
                line_surface = font.render(line, True, color)
                screen.blit(line_surface, (rect.left, y))
                y += line_height
            except pygame.error as e:
                print(f"Warn: Render failed for line '{line[:10]}...': {e}")
                y += line_height

    def draw(self, screen):
        """Draws the chat history and input field with UI polish."""
        history_x = 10
        history_y = 10
        line_height = self.font.get_linesize()
        history_render_limit = line_height * MAX_CHAT_HISTORY
        max_history_width = SCREEN_WIDTH * 0.6  # Limit history width
        # Calculate actual height needed based on messages to draw
        messages_to_draw = list(self.history)[-MAX_CHAT_HISTORY:]
        # Simplified height, wrap complicates this
        actual_history_height = len(messages_to_draw) * line_height
        history_area_rect = pygame.Rect(history_x, history_y, max_history_width, min(
            history_render_limit, actual_history_height + 10))  # Adjust height slightly

        # *** ADDED: Draw semi-transparent background for history ***
        if messages_to_draw:  # Only draw if there's history
            history_bg_surf = pygame.Surface(
                history_area_rect.size, pygame.SRCALPHA)
            history_bg_surf.fill(CHAT_HISTORY_BG_COLOR)
            screen.blit(history_bg_surf, history_area_rect.topleft)

        # --- Draw History Text (on top of background) ---
        current_y = history_y + 5  # Start text slightly inside the bg rect
        for timestamp, sender, message in messages_to_draw:
            if current_y >= history_y + history_render_limit:
                break

            time_str = time.strftime("[%H:%M:%S]", time.localtime(timestamp))
            try:
                time_surf = self.font.render(
                    time_str, True, CHAT_TIMESTAMP_COLOR)
                time_rect = time_surf.get_rect(
                    left=history_x + 5, top=current_y)
                screen.blit(time_surf, time_rect)
                current_x = time_rect.right + 5
            except pygame.error as e:
                print(f"Warn: Render timestamp fail: {e}")
                current_x = history_x + 5

            username_color = self._get_color_for_username(sender)
            try:
                user_surf = self.font.render(sender, True, username_color)
                user_rect = user_surf.get_rect(left=current_x, top=current_y)
                screen.blit(user_surf, user_rect)
                current_x = user_rect.right
            except pygame.error as e:
                print(f"Warn: Render username fail: {e}")

            message_color = CHAT_MY_MESSAGE_COLOR if sender == self.my_username else CHAT_OTHER_MESSAGE_COLOR
            message_prefix = ": "
            try:
                prefix_surf = self.font.render(
                    message_prefix, True, message_color)
                prefix_rect = prefix_surf.get_rect(
                    left=current_x, top=current_y)
                screen.blit(prefix_surf, prefix_rect)
                text_start_x = prefix_rect.right
            except pygame.error as e:
                print(f"Warn: Render prefix fail: {e}")
                text_start_x = current_x + 5

            available_width = max(
                10, (history_x + max_history_width) - text_start_x)
            char_width_approx = self.font.size("A")[0]
            wrap_width = max(
                10, int(available_width / char_width_approx)) if char_width_approx > 0 else 20
            wrapped_lines = textwrap.wrap(
                message, width=wrap_width, replace_whitespace=False, drop_whitespace=False)

            start_line_y = current_y
            line_idx = 0
            for line in wrapped_lines:
                if current_y >= history_y + history_render_limit:
                    break
                try:
                    line_surf = self.font.render(line, True, message_color)
                    line_x = text_start_x if line_idx == 0 else text_start_x + 5  # Indent subsequent
                    screen.blit(line_surf, (line_x, current_y))
                    current_y += line_height
                    line_idx += 1
                except pygame.error as e:
                    print(f"Warn: Render chat line fail: {e}")
                    current_y += line_height
            if current_y == start_line_y:
                current_y += line_height  # Ensure Y advances even if rendering failed
            if current_y > history_y + history_render_limit:
                break

        # --- Draw Input Field (unchanged styling from previous) ---
        input_rect_base = pygame.Rect(5, SCREEN_HEIGHT - 5 - (self.input_font.get_linesize(
        ) + 8), SCREEN_WIDTH - 10, self.input_font.get_linesize() + 8)
        if self.active:
            prompt = "Say: "
            display_text = prompt + self.input_text
            if time.time() % 1.0 < 0.5:
                display_text += "_"
            pygame.draw.rect(screen, CHAT_INPUT_BOX_COLOR_ACTIVE,
                             input_rect_base, border_radius=3)
            pygame.draw.rect(screen, CHAT_INPUT_BORDER_COLOR_ACTIVE,
                             input_rect_base, width=1, border_radius=3)
            input_surf = self.input_font.render(
                display_text, True, CHAT_INPUT_ACTIVE_COLOR)
            input_rect = input_surf.get_rect(
                left=input_rect_base.left + 5, centery=input_rect_base.centery)
            screen.blit(input_surf, input_rect)
        else:
            hint_surf = self.font.render("[T] to chat", True, (150, 150, 150))
            hint_rect = hint_surf.get_rect(
                left=input_rect_base.left + 5, centery=input_rect_base.centery)
            # pygame.draw.rect(screen, CHAT_INPUT_BOX_COLOR_INACTIVE, input_rect_base, border_radius=3) # Optional inactive bg
            screen.blit(hint_surf, hint_rect)


# --- Renderer (Simplified) ---
class Renderer:  # ... (unchanged) ...
    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")
        pygame.font.init()
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)
        self.username_font = pygame.font.SysFont(None, 20)
        self.username_color = (230, 230, 230)
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

    def render_game_world(self, state_manager):
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
            return False
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
            return True

# --- Game Client (Uses Polished ChatManager) ---


class GameClient:  # ... (unchanged) ...
    def __init__(self):
        pygame.init()
        self.state_manager = GameStateManager()
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.input_handler = InputHandler()
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

    def _process_server_messages(self):
        try:
            while True:
                message_type, message_data = self.server_message_queue.get_nowait()
                if message_type == "map_data":
                    self.state_manager.set_initial_map_data(message_data)
                    _, _, _, ts = self.state_manager.get_map_data()
                    self.renderer.tile_size = ts
                elif message_type == "delta_update":
                    self.state_manager.apply_delta_update(message_data)
                elif message_type == "chat":
                    self.chat_manager.add_message(message_data)
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
        self.chat_manager.set_my_username(
            self.username)  # Set username in ChatManager

        self.running = True
        if not self.network_handler.start():
            print("Failed network start.")
            self.running = False
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        pygame.quit()
                        return
                render_ok = self.renderer.render_game_world(self.state_manager)
                # if render_ok: self.chat_manager.draw(self.renderer.screen) # Maybe omit chat on error screen
                pygame.display.flip()
                self.clock.tick(10)

        print("Waiting for player ID...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:
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
            message_to_send = None
            if self.input_handler.check_quit_event():
                self.running = False
                continue
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.chat_manager.is_active():
                            self.chat_manager.toggle_active()
                        else:
                            self.running = False
                            break
                    elif event.key == pygame.K_t and not self.chat_manager.is_active():
                        self.chat_manager.toggle_active()
                    elif self.chat_manager.is_active():
                        message_to_send = self.chat_manager.handle_input_event(
                            event)
            if not self.running:
                continue
            if not self.chat_manager.is_active():
                current_direction = self.input_handler.handle_events_for_movement()
                self.network_handler.update_input_direction(current_direction)
            else:
                self.network_handler.update_input_direction(
                    game_pb2.PlayerInput.Direction.UNKNOWN)
            if message_to_send:
                self.network_handler.send_chat_message(message_to_send)
            self._process_server_messages()
            render_ok = self.renderer.render_game_world(self.state_manager)
            if render_ok:
                self.chat_manager.draw(self.renderer.screen)
            pygame.display.flip()
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
