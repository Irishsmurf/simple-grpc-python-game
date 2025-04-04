# client/utils.py
import sys
import os


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # The base for relative paths is where the executable is (or _MEIPASS root)
        base_path = sys._MEIPASS
    except Exception:
        # If not running in PyInstaller bundle, use this file's directory's parent (client/)
        # Assuming utils.py is directly inside client/
        base_path = os.path.abspath(os.path.dirname(__file__))

    # Join the base path (bundle temp dir or script dir) with the relative path
    # Relative path should be like "assets/image.png" or "fonts/font.ttf"
    return os.path.join(base_path, relative_path)
