"""The app's icon as a multi-size .ico, from web/icon.png (the حرف mark; tools/icon/render.js draws it).
Usage: python make_icon.py out.ico"""
import sys
from pathlib import Path

from PIL import Image

src = Path(__file__).resolve().parent.parent / "web" / "icon.png"
Image.open(src).convert("RGBA").save(sys.argv[1], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
