from PIL import Image, ImageDraw
import os

# --- Configuration ---
SPRITE_SIZE = 32  # Dimensions of the sprite (e.g., 32x32 pixels)
# Simple bright color that contrasts with the dark blue background
FILL_COLOR = (255, 255, 0, 255)  # Yellow (R, G, B, Alpha)
OUTLINE_COLOR = (0, 0, 0, 255)    # Black outline (R, G, B, Alpha)
OUTPUT_DIR = "assets" # Relative path to assets directory
FILENAME = "player.png"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, FILENAME)

# --- Create Sprite ---
try:
    # Ensure the output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True) # exist_ok=True prevents error if dir exists

    # Create a new transparent image (RGBA)
    img = Image.new('RGBA', (SPRITE_SIZE, SPRITE_SIZE), (0, 0, 0, 0)) # Transparent background
    draw = ImageDraw.Draw(img)

    # Define bounding box for the circle (slightly smaller than the image size for outline)
    padding = 2 # Padding from edge
    bbox = [(padding, padding), (SPRITE_SIZE - padding -1, SPRITE_SIZE - padding -1)]

    # Draw a simple filled circle with an outline
    draw.ellipse(bbox, fill=FILL_COLOR, outline=OUTLINE_COLOR, width=1)

    # --- Save Sprite ---
    img.save(OUTPUT_PATH)
    print(f"Successfully created sprite: {OUTPUT_PATH}")

except Exception as e:
    print(f"Error creating sprite: {e}")