"""Genera l'icona dell'app (GP su fondo blu) senza dipendenze esterne oltre a Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out = Path(__file__).with_name("icona.ico")
img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(37, 99, 235, 255))
font = None
for f in ("C:/Windows/Fonts/segoeuib.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
    try:
        font = ImageFont.truetype(f, 120)
        break
    except OSError:
        pass
font = font or ImageFont.load_default(size=120)
d.text((128, 132), "GP", font=font, fill="white", anchor="mm")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
