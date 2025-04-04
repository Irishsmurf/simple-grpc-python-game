# client/input.py
import pygame

from gen.python import game_pb2


class InputHandler:
    """Handles user input for movement and quitting."""

    def __init__(self):
        self.current_direction = game_pb2.PlayerInput.Direction.UNKNOWN
        self.quit_requested = False

    def handle_movement_input(self) -> game_pb2.PlayerInput.Direction:
        """
        Checks pressed keys for movement. Should be called only when chat is inactive.
        Returns the current movement direction.
        """
        # Reset quit request flag when checking movement, assuming quit check is separate
        # self.quit_requested = False
        new_direction = game_pb2.PlayerInput.Direction.UNKNOWN

        # Use get_pressed for continuous movement checks
        keys_pressed = pygame.key.get_pressed()

        if keys_pressed[pygame.K_w] or keys_pressed[pygame.K_UP]:
            new_direction = game_pb2.PlayerInput.Direction.UP
        elif keys_pressed[pygame.K_s] or keys_pressed[pygame.K_DOWN]:
            new_direction = game_pb2.PlayerInput.Direction.DOWN
        elif keys_pressed[pygame.K_a] or keys_pressed[pygame.K_LEFT]:
            new_direction = game_pb2.PlayerInput.Direction.LEFT
        elif keys_pressed[pygame.K_d] or keys_pressed[pygame.K_RIGHT]:
            new_direction = game_pb2.PlayerInput.Direction.RIGHT

        # Update internal state only if direction changed
        if self.current_direction != new_direction:
            self.current_direction = new_direction

        return self.current_direction

    def check_quit_event(self) -> bool:
        """
        Checks the event queue *only* for the QUIT event (window close).
        Sets the internal quit_requested flag if found.
        Returns True if QUIT was found, False otherwise.
        Call this once per frame in the main loop.
        """
        # Important: This consumes QUIT events from the queue
        for event in pygame.event.get(eventtype=pygame.QUIT):
            self.quit_requested = True
            return True
        return False

    def should_quit(self) -> bool:
        """Returns True if a quit event has been detected."""
        return self.quit_requested
