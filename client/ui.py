# client/ui.py
import pygame
import time
import textwrap
import hashlib
from collections import deque
from typing import Union

from gen.python import game_pb2

# Import config and utils
from .config import (SCREEN_WIDTH, SCREEN_HEIGHT, BACKGROUND_COLOR,
                     SPRITE_SHEET_PATH, TILESET_PATH, FONT_PATH, FRAME_WIDTH, FRAME_HEIGHT,
                     MAX_CHAT_HISTORY, CHAT_INPUT_MAX_LEN, CHAT_DISPLAY_WIDTH,
                     CHAT_TIMESTAMP_COLOR, CHAT_DEFAULT_USERNAME_COLOR, CHAT_MY_MESSAGE_COLOR,
                     CHAT_OTHER_MESSAGE_COLOR, CHAT_INPUT_PROMPT_COLOR, CHAT_INPUT_ACTIVE_COLOR,
                     CHAT_INPUT_BOX_COLOR_ACTIVE, CHAT_INPUT_BOX_COLOR_INACTIVE,
                     CHAT_INPUT_BORDER_COLOR_ACTIVE, CHAT_HISTORY_BG_COLOR)
from .utils import resource_path


class ChatManager:
    """Handles chat UI state, input, and rendering with UI polish."""

    def __init__(self, max_history=MAX_CHAT_HISTORY):
        self.active = False
        self.input_text = ""
        # Stores tuples: (timestamp, sender_username, message_text)
        self.history = deque(maxlen=max_history)
        self.my_username = ""  # Will be set later by GameClient

        # Load font (handle potential error)
        try:
            self.font = pygame.font.Font(FONT_PATH, 14)  # Size for history
            self.input_font = pygame.font.Font(
                FONT_PATH, 16)  # Slightly larger for input
            print(f"ChatManager: Loaded font '{FONT_PATH}'")
        except pygame.error as e:
            print(
                f"Warning: Could not load font '{FONT_PATH}'. Using default SysFont. Error: {e}")
            self.font = pygame.font.SysFont(None, 22)  # Fallback history font
            self.input_font = pygame.font.SysFont(
                None, 24)  # Fallback input font

    def set_my_username(self, username: str):
        """Stores the local player's username for highlighting."""
        self.my_username = username

    def _get_color_for_username(self, username: str) -> tuple[int, int, int]:
        """Generates a deterministic color based on username hash."""
        if not username:
            return CHAT_DEFAULT_USERNAME_COLOR
        # Use SHA1 hash and map bytes to RGB values
        hasher = hashlib.sha1(username.encode('utf-8'))
        hash_bytes = hasher.digest()
        # Generate RGB, ensuring values are reasonably bright (100-255 range)
        r = 100 + (hash_bytes[0] % 156)
        g = 100 + (hash_bytes[1] % 156)
        b = 100 + (hash_bytes[2] % 156)
        return (r, g, b)

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

    def is_active(self) -> bool:
        """Returns True if chat input is active."""
        return self.active

    def add_message(self, chat_message_proto: game_pb2.ChatMessage):
        """Adds a received message with timestamp to history."""
        timestamp = time.time()
        self.history.append(
            (timestamp, chat_message_proto.sender_username, chat_message_proto.message_text))

    def handle_input_event(self, event: pygame.event.Event) -> Union[str, None]:
        """
        Processes a Pygame KEYDOWN event when chat is active.
        Returns the message string to send if Enter was pressed, else None.
        Handles deactivation on Enter/Esc.
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
            # Add length limit check
            if len(self.input_text) < CHAT_INPUT_MAX_LEN:
                self.input_text += event.unicode

        if deactivate_chat:
            self.toggle_active()  # Use toggle to handle state change and key repeat

        return message_to_send  # Return the message string or None

    def draw(self, screen: pygame.Surface):
        """Draws the chat history and input field with UI polish."""
        history_x = 10
        history_y = 10
        line_height = self.font.get_linesize()
        history_render_limit = line_height * MAX_CHAT_HISTORY
        max_history_width = SCREEN_WIDTH * 0.6  # Limit history width
        messages_to_draw = list(self.history)  # Get a copy of recent messages
        actual_history_height = len(
            messages_to_draw) * line_height  # Simplified height
        history_area_rect = pygame.Rect(history_x - 2, history_y - 2, max_history_width + 4, min(
            history_render_limit, actual_history_height + 4))  # Pad rect slightly

        # --- Draw History Background ---
        if messages_to_draw:
            history_bg_surf = pygame.Surface(
                history_area_rect.size, pygame.SRCALPHA)
            history_bg_surf.fill(CHAT_HISTORY_BG_COLOR)
            screen.blit(history_bg_surf, history_area_rect.topleft)

        # --- Draw History Text ---
        current_y = history_y
        for timestamp, sender, message in messages_to_draw:
            if current_y >= history_y + history_render_limit:
                break

            time_str = time.strftime("[%H:%M:%S]", time.localtime(timestamp))
            try:
                time_surf = self.font.render(
                    time_str, True, CHAT_TIMESTAMP_COLOR)
                time_rect = time_surf.get_rect(left=history_x, top=current_y)
                screen.blit(time_surf, time_rect)
                current_x = time_rect.right + 5
            except pygame.error as e:
                print(f"Warn: Render timestamp fail: {e}")
                current_x = history_x

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
                    line_x = text_start_x  # Keep same indent for wrapped lines
                    screen.blit(line_surf, (line_x, current_y))
                    current_y += line_height
                    line_idx += 1
                except pygame.error as e:
                    print(f"Warn: Render chat line fail: {e}")
                    current_y += line_height
            if current_y == start_line_y:
                current_y += line_height
            if current_y > history_y + history_render_limit:
                break

        # --- Draw Input Field ---
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


class Renderer:
    """Handles Pygame rendering for the game world (map, players)."""

    def __init__(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Simple gRPC Game Client")
        pygame.font.init()  # Still need font init for player names etc.
        self.error_font = pygame.font.SysFont(None, 26)
        self.error_text_color = (255, 100, 100)
        # Font for player names above sprite
        self.username_font = pygame.font.SysFont(None, 20)
        self.username_color = (230, 230, 230)

        self.directional_frames = {}
        self.tile_graphics = {}
        self.player_rect = None
        self.tile_size = 32  # Default
        self._load_assets()
        self.camera_x = 0.0
        self.camera_y = 0.0

    def _load_assets(self):
        """Loads game assets (sprites, tileset)."""
        print("Renderer: Loading assets...")
        try:
            # Tileset
            tileset_img = pygame.image.load(TILESET_PATH).convert_alpha()
            print(f"Renderer: Loaded tileset from {TILESET_PATH}")
            # TODO: Improve tile graphic extraction if tile size changes significantly
            self.tile_graphics[0] = tileset_img.subsurface(
                (0, 0, self.tile_size, self.tile_size))
            self.tile_graphics[1] = tileset_img.subsurface(
                (self.tile_size, 0, self.tile_size, self.tile_size))

            # Player Sprite Sheet
            sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
            print(f"Renderer: Loaded sprite sheet from {SPRITE_SHEET_PATH}")
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
            raise  # Propagate error

    def update_camera(self, target_x, target_y, world_width, world_height):
        """Updates the camera position based on the target (player)."""
        target_cam_x = target_x - self.screen_width / 2
        target_cam_y = target_y - self.screen_height / 2
        if world_width > self.screen_width:
            self.camera_x = max(
                0.0, min(target_cam_x, world_width - self.screen_width))
        else:
            self.camera_x = (world_width - self.screen_width) / 2
        if world_height > self.screen_height:
            self.camera_y = max(
                0.0, min(target_cam_y, world_height - self.screen_height))
        else:
            self.camera_y = (world_height - self.screen_height) / 2

    def draw_map(self, map_data, map_w, map_h, tile_size):
        """Draws the visible portion of the map."""
        if not map_data or tile_size <= 0:
            return
        if self.tile_size != tile_size:
            self.tile_size = tile_size  # Update size if needed

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
        """Draws the players and their usernames."""
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

                # Tinting
                tsurf = surf.copy()
                color = player_colors.get(pid, (255, 255, 255))
                tisurf = pygame.Surface(prect.size, pygame.SRCALPHA)
                tisurf.fill(color+(128,))
                tsurf.blit(tisurf, (0, 0),
                           special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(tsurf, prect)

                # Player Username (above sprite)
                if player.username:
                    usurf = self.username_font.render(
                        player.username, True, self.username_color)
                    urect = usurf.get_rect(
                        centerx=prect.centerx, bottom=prect.top-2)
                    self.screen.blit(usurf, urect)

                # Highlight own player
                if pid == my_player_id:
                    pygame.draw.rect(
                        self.screen, (255, 255, 255), prect.inflate(4, 4), 2)

    def draw_error_message(self, message):
        """Draws an error message centered on the screen."""
        surf = self.error_font.render(message, True, self.error_text_color)
        rect = surf.get_rect(
            center=(self.screen_width//2, self.screen_height//2))
        self.screen.blit(surf, rect)

    def render_game_world(self, state_manager):
        """Renders the map and players. Returns False if an error was displayed."""
        error_msg = state_manager.get_connection_error()
        if error_msg:
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_error_message(error_msg)
            return False  # Error displayed
        else:
            # Get data needed for rendering
            current_player_map = state_manager.get_state_snapshot_map()
            map_data, map_w, map_h, tile_size = state_manager.get_map_data()
            my_player_id = state_manager.get_my_player_id()
            player_colors = state_manager.get_all_player_colors()

            # Update camera
            my_player_snapshot = current_player_map.get(my_player_id)
            if my_player_snapshot:
                world_w, world_h = state_manager.get_world_dimensions()
                self.update_camera(my_player_snapshot.x_pos,
                                   my_player_snapshot.y_pos, world_w, world_h)

            # Draw elements
            self.screen.fill(BACKGROUND_COLOR)
            self.draw_map(map_data, map_w, map_h, tile_size)
            self.draw_players(current_player_map, player_colors, my_player_id)
            return True  # Render successful
