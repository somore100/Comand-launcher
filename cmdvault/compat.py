"""Optional third-party dependencies. Each HAVE_* flag says whether the
feature that needs it is available; the module aliases are None when missing."""
try:
    from pynput import keyboard as pynput_keyboard
    HAVE_PYNPUT = True
except Exception:
    pynput_keyboard = None
    HAVE_PYNPUT = False

try:
    from PIL import Image as PILImage, ImageDraw as PILImageDraw
    HAVE_PIL = True
except Exception:
    PILImage = PILImageDraw = None
    HAVE_PIL = False

try:
    import pystray
    HAVE_PYSTRAY = HAVE_PIL
except Exception:
    pystray = None
    HAVE_PYSTRAY = False
