# client/main.py
from . import (
    config,
    state,
    network,
    input,
    ui
)
from . import config
import queue
import traceback
import time
import sys
import pygame
print("Client main.py: Starting up...")

try:
    from gen.python import game_pb2
except ModuleNotFoundError as e:
    print(
        f"main.py: Error importing generated code. Did you run 'protoc' and create gen/__init__.py / gen/python/__init__.py? Error: {e}")
    game_pb2 = None  # Allow limited continuation if only used for type hints
    sys.exit(1)


class GameClient:
    """Main game client class orchestrating all components."""

    def __init__(self):
        print("Initializing Pygame...")
        pygame.init()
        print("Initializing Components...")
        self.state_manager = state.GameStateManager()
        self.renderer = ui.Renderer(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        self.input_handler = input.InputHandler()
        self.chat_manager = ui.ChatManager()  # Instantiate ChatManager
        self.clock = pygame.time.Clock()
        self.server_message_queue = queue.Queue()  # Queue for messages from network thread
        self.network_handler = network.NetworkHandler(
            config.SERVER_ADDRESS, self.state_manager, self.server_message_queue)
        self.running = False
        self.username = ""
        print("GameClient Initialized.")

    def get_username_input(self):
        """Displays a simple screen to input username."""
        # This UI is basic, consider a dedicated UI framework for more complex input
        input_active = True
        input_text = ""
        # Use fonts loaded by Renderer or ChatManager if needed, or load here
        prompt_font = pygame.font.SysFont(None, 40)
        input_font = pygame.font.SysFont(None, 35)
        prompt_surf = prompt_font.render(
            "Enter Username:", True, (200, 200, 255))
        prompt_rect = prompt_surf.get_rect(
            center=(config.SCREEN_WIDTH//2, config.SCREEN_HEIGHT//2-50))
        instr_surf = input_font.render(
            "(Press Enter to join, Esc to quit)", True, (150, 150, 150))
        instr_rect = instr_surf.get_rect(
            center=(config.SCREEN_WIDTH//2, config.SCREEN_HEIGHT//2+50))

        while input_active:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None  # Indicate quit
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        if input_text:  # Require non-empty username
                            input_active = False
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.key == pygame.K_ESCAPE:  # Allow quitting from username screen
                        return None
                    elif len(input_text) < 16:  # Username length limit
                        # Basic alphanumeric + underscore/dash filter
                        if event.unicode.isalnum() or event.unicode in ['_', '-']:
                            input_text += event.unicode

            # Drawing for input screen
            self.renderer.screen.fill(config.BACKGROUND_COLOR)
            self.renderer.screen.blit(prompt_surf, prompt_rect)
            self.renderer.screen.blit(instr_surf, instr_rect)
            input_surf = input_font.render(input_text, True, (255, 255, 255))
            input_rect = input_surf.get_rect(
                center=(config.SCREEN_WIDTH//2, config.SCREEN_HEIGHT//2))
            pygame.draw.rect(self.renderer.screen, (50, 50, 100), input_rect.inflate(
                20, 10), border_radius=5)  # Input box bg
            self.renderer.screen.blit(input_surf, input_rect)
            pygame.display.flip()
            self.clock.tick(30)  # Lower FPS for input screen

        return input_text

    def _process_server_messages(self):
        """Processes messages received from the network thread."""
        try:
            while True:  # Process all available messages
                message_type, message_data = self.server_message_queue.get_nowait()

                if message_type == "map_data":
                    self.state_manager.set_initial_map_data(message_data)
                    # Update renderer's tile size if needed (Renderer checks internally now)
                    _, _, _, tile_size = self.state_manager.get_map_data()
                    if self.renderer.tile_size != tile_size:
                        print(
                            f"Client: Updating renderer tile size to {tile_size}")
                        self.renderer.tile_size = tile_size
                        # TODO: Potentially trigger re-extraction of tile graphics in renderer here
                elif message_type == "delta_update":
                    self.state_manager.apply_delta_update(message_data)
                elif message_type == "chat":
                    # Pass received chat message to ChatManager
                    self.chat_manager.add_message(message_data)
                else:
                    print(f"Warn: Unknown queue msg type: {message_type}")
        except queue.Empty:
            pass  # No more messages for now
        except Exception as e:
            print(f"Error processing server message queue: {e}")
            traceback.print_exc()  # Print full traceback for queue errors

    def run(self):
        """Main game loop."""
        self.username = self.get_username_input()
        if self.username is None:  # User quit during input
            self.shutdown()
            return

        print(f"Client: Username entered: {self.username}")
        self.network_handler.set_username(self.username)
        self.chat_manager.set_my_username(self.username)  # Inform ChatManager

        # --- Start Network and Main Loop ---
        self.running = True
        if not self.network_handler.start():
            print("Failed to start network handler. Exiting.")
            self.running = False
            # Error display loop
            while True:
                # Check only for quit events on error screen
                quit_event = False
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                        quit_event = True
                        break
                if quit_event:
                    break  # Exit loop to shutdown

                render_ok = self.renderer.render_game_world(self.state_manager)
                # Optionally draw chat manager's state even on error? Probably not.
                # if render_ok: self.chat_manager.draw(self.renderer.screen)
                pygame.display.flip()
                self.clock.tick(10)  # Low FPS for error screen
            self.shutdown()  # Shutdown after error screen exit
            return

        # Wait briefly for player ID to arrive from server after connection
        print("Waiting for player ID from server...")
        wait_start_time = time.time()
        while self.state_manager.get_my_player_id() is None and self.running:
            self._process_server_messages()  # Process any initial messages
            if self.network_handler.stop_event.is_set():  # Check if network thread died
                print("Network thread stopped while waiting for player ID. Exiting.")
                self.running = False
                break
            if time.time() - wait_start_time > 10:  # Timeout waiting for ID
                print("Error: Timed out waiting for player ID from server.")
                self.state_manager.set_connection_error(
                    "Timeout waiting for player ID.")
                self.running = False
                break
            time.sleep(0.05)  # Small sleep to avoid busy-waiting

        if not self.running:  # Check if waiting loop exited due to error/timeout
            self.shutdown()
            return

        print("Starting main game loop...")
        # Default direction
        current_direction = game_pb2.PlayerInput.Direction.UNKNOWN if game_pb2 else 0
        while self.running:
            # --- Check for Stop Signals ---
            if self.network_handler.stop_event.is_set():
                print("Stop event detected from network thread. Exiting loop.")
                self.running = False
                continue
            if self.input_handler.check_quit_event():  # Check for window close
                self.running = False
                continue

            # --- Process Events (Keyboard, etc.) ---
            message_to_send = None
            for event in pygame.event.get():  # Iterate through other events
                if event.type == pygame.KEYDOWN:
                    # Global ESC: Close chat if active, else quit game
                    if event.key == pygame.K_ESCAPE:
                        if self.chat_manager.is_active():
                            self.chat_manager.toggle_active()  # Close chat
                        else:
                            self.running = False
                            break  # Quit game
                    # Chat Toggle 'T'
                    elif event.key == pygame.K_t and not self.chat_manager.is_active():
                        self.chat_manager.toggle_active()
                    # Pass other keydown events to ChatManager if it's active
                    elif self.chat_manager.is_active():
                        message_to_send = self.chat_manager.handle_input_event(
                            event)
                # Handle other event types here if needed (e.g., MOUSEBUTTONDOWN)

            if not self.running:
                continue  # Check if ESC quit loop

            # --- Handle Movement / Update Network Input ---
            if not self.chat_manager.is_active():
                # Get movement direction from InputHandler (checks get_pressed)
                current_direction = self.input_handler.handle_movement_input()
                self.network_handler.update_input_direction(current_direction)
            else:
                # Ensure player stops moving when chat is active
                self.network_handler.update_input_direction(
                    game_pb2.PlayerInput.Direction.UNKNOWN if game_pb2 else 0)

            # --- Send Chat Message ---
            if message_to_send:
                self.network_handler.send_chat_message(message_to_send)

            # --- Process Incoming Server Messages ---
            self._process_server_messages()

            # --- Rendering ---
            render_ok = self.renderer.render_game_world(self.state_manager)
            # Only draw chat if game world rendered ok (no connection error)
            if render_ok:
                # Draw chat UI on top
                self.chat_manager.draw(self.renderer.screen)

            pygame.display.flip()  # Update the full screen surface
            # --- End Rendering ---

            self.clock.tick(config.FPS)  # Cap the frame rate

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
    # Ensure Pygame initializes fonts correctly before GameClient uses them
    pygame.init()
    pygame.font.init()  # Explicitly init font system
    print('lol')

    client = GameClient()
    try:
        client.run()
    except Exception as e:
        print(f"An unexpected error occurred in the main client: {e}")
        traceback.print_exc()
        # Attempt graceful shutdown on error
        try:
            client.shutdown()
        except Exception as shutdown_e:
            print(f"Error during shutdown: {shutdown_e}")
    finally:
        # Ensure pygame quits even if shutdown fails
        if pygame.get_init():
            pygame.quit()
