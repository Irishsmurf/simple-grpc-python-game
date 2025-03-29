import grpc
import threading
import time
import sys
import readchar
import pygame

# Import generated code (assuming 'gen/python' is accessible)
# Adjust sys.path if your structure differs or use package installation
import sys
import os
# Add the parent directory ('simple-grpc-game') to sys.path to find 'gen'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from gen.python import game_pb2
    from gen.python import game_pb2_grpc
except ModuleNotFoundError as e:
    print(e)
    print("Error: Could not find generated Proto/gRPC Python code.")
    print("Ensure 'protoc' was run correctly and 'gen/python' is in the Python path.")
    sys.exit(1)


SERVER_ADDRESS = "localhost:50051" # Server address and port
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50) # Dark blue
PLAYER_SPRITE_PATH = "assets/player_large.png"
SPRITE_SHEET_PATH = "assets/player_sheet_256.png"
FRAME_WIDTH = 128
FRAME_HEIGHT = 128
RUNNING_SHEET_PATH = "assets/running_sheet.png"
FPS = 60
TILESET_PATH = "assets/tileset.png" # Path to tileset image

world_map_data = None
world_pixel_width = 0.0
world_pixel_height = 0.0
tile_size = 32 # Size of each tile in pixels

map_width_tiles = 0
map_height_tiles = 0
map_lock = threading.Lock()
tile_graphics = {}

my_player_id = None
player_colors = {}
color_lock = threading.Lock()
AVAILABLE_COLORS = [
    (255, 255, 0),   # Yellow (Original)
    (0, 255, 255),   # Cyan
    (255, 0, 255),   # Magenta
    (0, 255, 0),     # Green
    (255, 165, 0),   # Orange
    (255, 255, 255), # White
]
next_color_index = 0


latest_game_state = None
state_lock = threading.Lock()

current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
direction_lock = threading.Lock()

camera_x, camera_y = 0, 0

def listen_for_updates(stub):
    """
    Listens for GameState updates from the server stream in a separate thread.
    Also handles sending PlayerInput messages periodically or on change.
    """
    global latest_game_state, next_color_index, my_player_id
    global world_map_data, map_width_tiles, map_height_tiles
    global world_pixel_width, world_pixel_height, tile_size

    print("Connecting to stream...")
    try:
        # --- Start the bidirectional stream ---
        # We need to send *something* initially, or structure it to wait
        # Let's send an initial UNKNOWN input to kick things off
        def input_generator():
            global latest_input
            global current_direction
            last_sent_direction = None
            while True:
                # Simple logic: Send input if it changed, or periodically?
                # Let's send if it changed since last time.
                dir_to_send = game_pb2.PlayerInput.Direction.UNKNOWN
                with direction_lock:
                    dir_to_send = current_direction
                yield game_pb2.PlayerInput(direction=dir_to_send)

                time.sleep(0.1 / 30.0) # Adjust sleep time as needed (controls input send rate)

        stream = stub.GameStream(input_generator())
        print("Stream started. Waiting for game state updates...")

        try:
            first_message = next(stream) # Get the first message
            if first_message and first_message.HasField("initial_map_data"):
                map_proto = first_message.initial_map_data
                print(f"Received map data: {map_proto.tile_width}x{map_proto.tile_height} tiles")
                my_player_id = map_proto.assigned_player_id
                print(f"*** Received own player ID: {my_player_id} ***")
                
                temp_map = []
                for y in range(map_proto.tile_height):
                    row_proto = map_proto.rows[y]
                    temp_map.append(list(row_proto.tiles))
                with map_lock:
                    world_map_data = temp_map
                    map_width_tiles = map_proto.tile_width
                    map_height_tiles = map_proto.tile_height
                    world_pixel_height = map_proto.world_pixel_height
                    world_pixel_width = map_proto.world_pixel_width
                    tile_size = map_proto.tile_size_pixels
                    print(f"World size: {world_pixel_width}x{world_pixel_height} px, Tile size: {tile_size}")

            else:
                 print("Warning: Did not receive valid map data.")
        except StopIteration:
            print("Error: Stream closed before map data received.")
            return 
        
        # --- Receive Loop ---
        for message in stream:
            if message and message.HasField('game_state'):
                state = message.game_state
                with state_lock:
                    latest_game_state = state
                with color_lock:
                    for p in state.players:
                        if p.id not in player_colors:
                            player_colors[p.id] = AVAILABLE_COLORS[next_color_index % len(AVAILABLE_COLORS)]
                            next_color_index += 1


    except grpc.RpcError as e:
        print(f"Error receiving game state: {e.code()} - {e.details()} - {e.debug_error_string()}")
    except Exception as e:
        print(f"An unexpected error occurred in listener thread: {e}")
    finally:
        print("Listener thread finished.")

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
    global latest_game_state, current_direction, my_player_id
    global camera_x, camera_y, world_pixel_width, world_pixel_height, tile_size

    pygame.init()
    pygame.display.set_caption("Simple gRPC Game Client")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    player_sprites = {}
    directional_frames = {}
    fallback_player_img = None
    player_rect = pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT)

    # Load Assets
    try:
        # Tile Assets
        tileset_img = pygame.image.load(TILESET_PATH).convert_alpha()
        print(f"Loaded tileset from {TILESET_PATH}")
        tile_graphics[0] = tileset_img.subsurface((0, 0, tile_size, tile_size)) # Grass tile
        tile_graphics[1] = tileset_img.subsurface((tile_size, 0, tile_size, tile_size)) # Wall tile
        print(f"Loaded {len(tile_graphics)} tile graphics.")

        # Player Sprite
        player_img = pygame.image.load(PLAYER_SPRITE_PATH).convert_alpha()
        player_rect = player_img.get_rect()
        print(f"Loaded player sprite from {PLAYER_SPRITE_PATH}")

        sheet_img = pygame.image.load(SPRITE_SHEET_PATH).convert_alpha()
        print(f"Loaded sprite sheet from {SPRITE_SHEET_PATH}")
        
        up_rect = pygame.Rect(0, 0, FRAME_WIDTH, FRAME_HEIGHT)
        down_rect = pygame.Rect(FRAME_WIDTH, 0, FRAME_WIDTH, FRAME_HEIGHT)
        left_rect = pygame.Rect(0, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
        right_rect = pygame.Rect(FRAME_WIDTH, FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
        directional_frames[game_pb2.AnimationState.RUNNING_UP] = sheet_img.subsurface(up_rect)
        directional_frames[game_pb2.AnimationState.RUNNING_DOWN] = sheet_img.subsurface(down_rect)
        directional_frames[game_pb2.AnimationState.RUNNING_LEFT] = sheet_img.subsurface(left_rect)
        directional_frames[game_pb2.AnimationState.RUNNING_RIGHT] = sheet_img.subsurface(right_rect)
        directional_frames[game_pb2.AnimationState.IDLE] = sheet_img.subsurface(down_rect)
        directional_frames[game_pb2.AnimationState.UNKNOWN_STATE] = sheet_img.subsurface(down_rect)

        print(f"Extracted {len(directional_frames)} directional frames.")
        player_rect = directional_frames[game_pb2.AnimationState.IDLE].get_rect()        

    except pygame.error as e:
        print(f"Error loading player sprite: {e}")
        print("Ensure the asset path is correct and the file exists.")
        pygame.quit()
        return
    
    channel = None
    listener_thread = None
    print(f"Attempting to connect to server at {SERVER_ADDRESS}...")
    try:
        channel = grpc.insecure_channel(SERVER_ADDRESS)
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
            print("Channel connected.")
        except grpc.FutureTimeoutError:
            print(f"Error: Connection timed out after 5 seconds. Is the server running at {SERVER_ADDRESS}?")
            raise
        stub = game_pb2_grpc.GameServiceStub(channel)
        listener_thread = threading.Thread(target=listen_for_updates, args=(stub,), daemon=True)
        listener_thread.start()
        print("Listener thread started.")
        time.sleep(0.5)
        print(f"DEBUG: run() starting main look. my_player_id = {my_player_id}")

        # Main loop
        running = True
        my_player_snapshot = None
        while running:
            while my_player_id is None:
                if listener_thread and not listener_thread.is_alive():
                    print("Error: Listener thread terminated before Player ID")
                    running = False
                    break
                print("Waiting for player id...")
                time.sleep(0.1)
                if not running:
                    continue

            new_direction = game_pb2.PlayerInput.Direction.UNKNOWN
            keys_pressed = pygame.key.get_pressed()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]:
                new_direction = game_pb2.PlayerInput.Direction.UP
            elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]:
                new_direction = game_pb2.PlayerInput.Direction.DOWN
            elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]:
                new_direction = game_pb2.PlayerInput.Direction.LEFT
            elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]:
                new_direction = game_pb2.PlayerInput.Direction.RIGHT

            with direction_lock:
                if current_direction != new_direction:
                    current_direction = new_direction
                    print(f"Direction changed to {game_pb2.PlayerInput.Direction.Name(current_direction)}")
            

            current_state_snapshot = None
            assigned_colors = {}
            local_id = my_player_id
            my_player_snapshot = None

            with state_lock:
                if latest_game_state is not None:
                    current_state_snapshot = latest_game_state
                    for p in current_state_snapshot.players:
                        if p.id == local_id:
                            my_player_snapshot = p
                            break
            with color_lock:
                assigned_colors = player_colors.copy()

            if my_player_snapshot:
                target_cam_x = my_player_snapshot.x_pos - SCREEN_WIDTH / 2
                target_cam_y = my_player_snapshot.y_pos - SCREEN_HEIGHT / 2
                
                if world_pixel_width > SCREEN_WIDTH:
                    camera_x = max(0.0, min(target_cam_x, world_pixel_width - SCREEN_WIDTH))
                else:
                    camera_x = (world_pixel_width - SCREEN_WIDTH) / 2

                if world_pixel_height > SCREEN_HEIGHT:
                    camera_y = max(0.0, min(target_cam_y, world_pixel_height - SCREEN_HEIGHT))
                else:
                    camera_y = (world_pixel_height - SCREEN_HEIGHT) / 2

            screen.fill(BACKGROUND_COLOR)
            # Draw the map
            local_map_data = None
            map_w, map_h = 0, 0
            current_tile_size = 32
            with map_lock:
                local_map_data = world_map_data
                map_w = map_width_tiles
                map_h = map_height_tiles
                if tile_size > 0:
                    current_tile_size = tile_size
            if local_map_data:
                start_tile_x = max(0, int(camera_x / current_tile_size))
                end_tile_x = min(map_w, int((camera_x + SCREEN_WIDTH) / current_tile_size))
                start_tile_y = max(0, int(camera_y / current_tile_size))
                end_tile_y = min(map_h, int((camera_y + SCREEN_HEIGHT) / current_tile_size))

                for y in range(start_tile_y, end_tile_y):
                    for x in range(start_tile_x, end_tile_x):
                        tile_id = local_map_data[y][x]
                        if tile_id in tile_graphics:
                            tile_surface = tile_graphics[tile_id]
                            screen_x = x * current_tile_size - camera_x
                            screen_y = y * current_tile_size - camera_y
                            screen.blit(tile_surface, (screen_x, screen_y))

            if current_state_snapshot:
                for player in current_state_snapshot.players:
                    player_state = player.current_animation_state
                    current_frame_surface = directional_frames.get(player_state, directional_frames[game_pb2.AnimationState.UNKNOWN_STATE])
                    
                    if current_frame_surface:
                        screen_x = player.x_pos - camera_x
                        screen_y = player.y_pos - camera_y
                        player_rect = current_frame_surface.get_rect()
                        player_rect.center = (int(screen_x), int(screen_y))

                        temp_sprite_frame = current_frame_surface.copy()
                        color = assigned_colors.get(player.id, (255, 255, 255))
                        tint_surface = pygame.Surface(player_rect.size, pygame.SRCALPHA)
                        tint_surface.fill(color + (255,))  # Semi-transparent tint
                        temp_sprite_frame.blit(tint_surface, (0,0), special_flags=pygame.BLEND_RGBA_MULT)

                        if player.id == local_id:
                            pygame.draw.rect(screen, (255, 255, 255), player_rect.inflate(4, 4), 2)
                        screen.blit(temp_sprite_frame, player_rect)
            
            pygame.display.flip()
            clock.tick(FPS)

    except grpc.RpcError as e:
        print(f"gRPC error: {e.code()} - {e.details()} - {e.debug_error_string()}")
    except Exception as e:
        print(f"An error occurred in the main loop or connection: {e}")
    finally:
        if channel:
            channel.close()
        pygame.quit()
        if listener_thread and listener_thread.is_alive():
            print("Waiting for listener thread to finish...")
            listener_thread.join(timeout=0.5)
        pygame.quit()
        print("Client shut down.")

if __name__ == "__main__":
    run()