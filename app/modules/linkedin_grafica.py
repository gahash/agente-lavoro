"""Grafiche dei post LinkedIn: un'immagine quadrata 1200x1200 per post, con lo stile del CV.

Titolo = prima frase del post, punti = le righe che iniziano con •, →, - o un numero.
Le immagini stanno in dati/linkedin/ e si allegano al post su LinkedIn trascinandole.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..core.config import DATA, load_settings

CARTELLA = DATA / "linkedin"
LATO = 1200
FONDO, FONDO2 = (19, 32, 43), (15, 61, 66)
ACCENTO, CHIARO, TENUE = (94, 234, 212), (241, 245, 249), (148, 163, 184)

_FONT = {
    "darwin": {"titolo": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
               "testo": "/System/Library/Fonts/Supplemental/Arial.ttf",
               "grassetto": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "win32": {"titolo": r"C:\Windows\Fonts\georgiab.ttf", "testo": r"C:\Windows\Fonts\arial.ttf",
              "grassetto": r"C:\Windows\Fonts\arialbd.ttf"},
}


def _font(tipo: str, size: int) -> ImageFont.FreeTypeFont:
    path = _FONT.get(sys.platform, {}).get(tipo)
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except OSError:
        return ImageFont.load_default(size)


def _a_capo(d: ImageDraw.ImageDraw, testo: str, font, larghezza: int) -> list[str]:
    righe, riga = [], ""
    for parola in testo.split():
        prova = f"{riga} {parola}".strip()
        if d.textlength(prova, font=font) <= larghezza:
            riga = prova
        else:
            righe.append(riga)
            riga = parola
    return righe + ([riga] if riga else [])


PUNTO = re.compile(r"^(?:[•→\-–▪]|\d+[.)])\s*(.+)")


def contenuto(testo: str) -> tuple[str, list[tuple[str, str]]]:
    """Titolo (prima frase) e voci della grafica: ("punto", testo) oppure ("intestazione", testo) quando un
    elenco è introdotto da una riga che finisce con ':' (es. "Cloud quando:"), così gli elenchi non si confondono."""
    righe = [r.strip() for r in (testo or "").splitlines() if r.strip() and not r.strip().startswith("#")]
    titolo = righe[0] if righe else ""
    voci = []
    for i, r in enumerate(righe[1:], 1):
        m = PUNTO.match(r)
        if m:
            t = m.group(1).rstrip(";:.")
            voci.append(("punto", t[:1].upper() + t[1:]))
        elif r.endswith(":") and i + 1 < len(righe) and PUNTO.match(righe[i + 1]) and len(r) < 70:
            voci.append(("intestazione", r))
    if not any(k == "intestazione" for k, _ in voci):
        voci = voci[:5]
    return titolo, voci


def disegna(testo: str, tema: str, destinazione: Path) -> Path:
    titolo, voci = contenuto(testo)
    img = Image.new("RGB", (LATO, LATO), FONDO)
    d = ImageDraw.Draw(img)
    for y in range(LATO):                                   # sfumatura diagonale leggera
        t = y / LATO
        d.line([(0, y), (LATO, y)], fill=tuple(int(FONDO[i] + (FONDO2[i] - FONDO[i]) * t * 0.9) for i in range(3)))
    m = 90
    d.rectangle([m, m, m + 120, m + 10], fill=ACCENTO)
    d.text((m, m + 40), tema.upper()[:60], font=_font("grassetto", 30), fill=ACCENTO)

    # titolo: riduce il carattere finché sta in 5 righe
    for size in (76, 68, 60, 54, 48):
        f = _font("titolo", size)
        righe = _a_capo(d, titolo, f, LATO - 2 * m)
        if len(righe) <= 5:
            break
    y = m + 110
    for r in righe[:5]:
        d.text((m, y), r, font=f, fill=CHIARO)
        y += int(size * 1.22)

    y += 40
    intestazioni = any(k == "intestazione" for k, _ in voci)
    fp = _font("testo", 30 if intestazioni else 34)
    fh = _font("grassetto", 30)
    passo = 40 if intestazioni else 46
    for tipo, testo_voce in voci:
        if tipo == "intestazione":
            if y + passo * 2 > LATO - 220:            # niente intestazione senza almeno un punto sotto
                break
            y += 6
            d.text((m, y), testo_voce, font=fh, fill=ACCENTO)
            y += passo + 4
            continue
        righe_p = _a_capo(d, testo_voce, fp, LATO - 2 * m - 50)[:2]
        if y + len(righe_p) * passo > LATO - 220:
            break
        d.ellipse([m, y + 11, m + 14, y + 25], fill=ACCENTO)
        for r in righe_p:
            d.text((m + 36, y), r, font=fp, fill=(203, 213, 225))
            y += passo
        y += 10 if intestazioni else 18

    s = load_settings()
    d.line([(m, LATO - 170), (LATO - m, LATO - 170)], fill=(51, 65, 85), width=2)
    d.text((m, LATO - 140), s["nome"], font=_font("grassetto", 38), fill=CHIARO)
    d.text((m, LATO - 90), "AI Engineer & Full-Stack Architect", font=_font("testo", 28), fill=TENUE)
    sito = s["sito"].replace("https://", "").replace("http://", "")
    fs = _font("grassetto", 30)
    d.text((LATO - m - d.textlength(sito, font=fs), LATO - 115), sito, font=fs, fill=ACCENTO)

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    img.save(destinazione, "PNG", optimize=True)
    return destinazione


def percorso(pid: int) -> Path:
    return CARTELLA / f"post_{pid}.png"
