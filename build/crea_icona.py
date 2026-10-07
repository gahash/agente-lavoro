"""Genera l'icona dell'app (GP su fondo blu) senza dipendenze esterne oltre a Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out = Path(__file__).with_name("icona.ico")
img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(37, 99, 235, 255))
try:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 120)
except OSError:
    font = ImageFont.load_default()
d.text((128, 132), "GP", font=font, fill="white", anchor="mm")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
