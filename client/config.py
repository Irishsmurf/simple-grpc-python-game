# client/config.py
from .utils import resource_path  # Import from local utils module

# Server/Network
# Remember to change if server address changes
SERVER_ADDRESS = "192.168.41.108:50051"
FPS = 60

# Screen
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (0, 0, 50)

# Assets (using resource_path)
SPRITE_SHEET_PATH = resource_path("assets/player_sheet_256.png")
TILESET_PATH = resource_path("assets/tileset.png")
# Assumes font is in client/fonts/
FONT_PATH = resource_path("fonts/DejaVuSansMono.ttf")

# Game Mechanics
FRAME_WIDTH = 128
FRAME_HEIGHT = 128

# Chat UI
MAX_CHAT_HISTORY = 7
CHAT_INPUT_MAX_LEN = 100
CHAT_DISPLAY_WIDTH = 70  # Approx characters width for wrapping
CHAT_TIMESTAMP_COLOR = (150, 150, 150)  # Grey for time
CHAT_DEFAULT_USERNAME_COLOR = (210, 210, 210)  # Default username color
CHAT_MY_MESSAGE_COLOR = (220, 220, 100)  # Yellowish for own messages
CHAT_OTHER_MESSAGE_COLOR = (255, 255, 255)  # White for others' messages
CHAT_INPUT_PROMPT_COLOR = (200, 255, 200)
CHAT_INPUT_ACTIVE_COLOR = (255, 255, 255)
CHAT_INPUT_BOX_COLOR_ACTIVE = (50, 50, 100)
CHAT_INPUT_BOX_COLOR_INACTIVE = (30, 30, 60)  # Slightly darker when inactive
CHAT_INPUT_BORDER_COLOR_ACTIVE = (150, 150, 255)
CHAT_HISTORY_BG_COLOR = (0, 0, 0, 150)  # Semi-transparent black

# Player Colors (Can also be here or loaded from elsewhere)
AVAILABLE_COLORS = [
    (255, 255, 0), (0, 255, 255), (255, 0, 255), (0, 255, 0),
    (255, 165, 0), (255, 255, 255)
]
