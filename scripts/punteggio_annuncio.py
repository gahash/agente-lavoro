"""Calcola il punteggio 1-10 di un annuncio secondo i pesi in config.yaml.

Uso interattivo:   python scripts/punteggio_annuncio.py
Uso da codice:     from punteggio_annuncio import punteggio
Ogni criterio vale da 0 (per nulla) a 1 (pienamente). I segnali di truffa azzerano il punteggio.
"""
from pathlib import Path

import yaml

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"))
PESI = CFG["ricerca_lavoro"]["pesi_punteggio"]
SOGLIA = CFG["ricerca_lavoro"]["soglia_contatto"]


def punteggio(valori: dict, sospetto: bool = False) -> tuple[float, str]:
    if sospetto:
        return 0.0, "Scartato: segnali di truffa"
    tot = sum(PESI[k] * max(0.0, min(1.0, float(valori.get(k, 0)))) for k in PESI)
    tot = round(max(1.0, tot), 1)
    dettagli = ", ".join(f"{k}={valori.get(k, 0)}" for k in PESI)
    azione = "CONTATTARE (bozza)" if tot >= SOGLIA else "archiviare"
    return tot, f"{dettagli} → {azione}"


if __name__ == "__main__":
    print("Valuta ogni criterio da 0 a 1 (es. 0.5).")
    v = {k: input(f"  {k} (peso {p}): ") or 0 for k, p in PESI.items()}
    s = input("  Segnali di truffa? (s/n): ").lower().startswith("s")
    print(punteggio(v, s))
