# client/state.py
import threading
from gen.python import game_pb2

# Import config constants if needed directly, or receive them via methods
from .config import AVAILABLE_COLORS


class GameStateManager:
    """Manages the client-side game state by applying delta updates."""

    def __init__(self):
        self.state_lock = threading.Lock()
        self.map_lock = threading.Lock()
        self.color_lock = threading.Lock()

        self.latest_game_state = game_pb2.GameState()  # Internal representation
        self.players_map = {}  # Map[player_id, Player_protobuf]

        self.my_player_id = None
        self.connection_error_message = None

        # Map data
        self.world_map_data = None
        self.map_width_tiles = 0
        self.map_height_tiles = 0
        self.world_pixel_width = 0.0
        self.world_pixel_height = 0.0
        self.tile_size = 32  # Default

        # Player appearance
        self.player_colors = {}
        self.next_color_index = 0

    def apply_delta_update(self, delta_update):
        """Applies changes from a DeltaUpdate message to the local state."""
        with self.state_lock, self.color_lock:  # Combine locks
            # Process removed players
            for removed_id in delta_update.removed_player_ids:
                if removed_id in self.players_map:
                    del self.players_map[removed_id]
                    # print(f"StateMgr: Player {removed_id} removed.") # Optional log
                if removed_id in self.player_colors:
                    del self.player_colors[removed_id]

            # Process updated/added players
            for updated_player in delta_update.updated_players:
                player_id = updated_player.id
                # Add or update player in the map
                self.players_map[player_id] = updated_player
                # Assign color if new
                if player_id not in self.player_colors:
                    self.player_colors[player_id] = AVAILABLE_COLORS[self.next_color_index % len(
                        AVAILABLE_COLORS)]
                    self.next_color_index += 1
                    # print(f"StateMgr: Player {player_id} added/updated.") # Optional log

    def get_state_snapshot_map(self):
        """Returns a *reference* to the internal players map. Use with caution or copy."""
        # This is efficient but requires careful handling by the caller (Renderer)
        with self.state_lock:
            return self.players_map

    def set_initial_map_data(self, map_proto):
        """Sets the initial map data and own player ID."""
        print(
            f"StateMgr: Received map data: {map_proto.tile_width}x{map_proto.tile_height} tiles")
        temp_map = []
        for y in range(map_proto.tile_height):
            # Ensure row exists before accessing tiles
            if y < len(map_proto.rows):
                temp_map.append(list(map_proto.rows[y].tiles))
            else:
                print(f"Warning: Missing row {y} in map data proto.")
                # Add empty row as fallback
                temp_map.append([0] * map_proto.tile_width)

        with self.map_lock:
            self.world_map_data = temp_map
            self.map_width_tiles = map_proto.tile_width
            self.map_height_tiles = map_proto.tile_height
            self.world_pixel_height = map_proto.world_pixel_height
            self.world_pixel_width = map_proto.world_pixel_width
            self.tile_size = map_proto.tile_size_pixels
            print(
                f"StateMgr: World set to {self.world_pixel_width}x{self.world_pixel_height}px, Tile Size: {self.tile_size}px")

        # Must set player ID outside map_lock but before returning control
        with self.state_lock:
            self.my_player_id = map_proto.assigned_player_id
            print(f"StateMgr: Received own player ID: {self.my_player_id}")

    def get_map_data(self):
        """Thread-safely gets map data."""
        with self.map_lock:
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
            # Default white
            return self.player_colors.get(player_id, (255, 255, 255))

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
