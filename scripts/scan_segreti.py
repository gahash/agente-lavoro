"""Scanner segreti di riserva (SOLA LETTURA) — da usare finche' gitleaks non e' installato.

Uso:  python scripts/scan_segreti.py <cartella-progetto> [--storia]

Cerca pattern di chiavi/token/password nei file di testo e, con --storia, anche
nella cronologia git (git log -p). NON stampa mai il segreto per intero: mostra
solo file, riga, tipo e un'anteprima mascherata. Report in reports/segreti-<nome>.md

Nota: e' un controllo euristico. Prima di qualunque push va ripetuto con gitleaks:
    gitleaks detect --source <cartella> --report-path reports/gitleaks-<nome>.json
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SALTA = {"node_modules", ".git", "vendor", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
EST_BINARIE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".mp4", ".mp3",
               ".woff", ".woff2", ".ttf", ".exe", ".dll", ".so", ".apk", ".aab", ".jar", ".lock"}

PATTERN = {
    "Chiave privata": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    "OpenAI key": r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",
    "Anthropic key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "Google API key": r"AIza[0-9A-Za-z_\-]{35}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "Stripe key": r"(?:sk|rk)_live_[0-9a-zA-Z]{20,}",
    "Twilio SID/key": r"\b(?:AC|SK)[0-9a-f]{32}\b",
    "Slack token": r"xox[baprs]-[0-9A-Za-z\-]{10,}",
    "JWT": r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "WhatsApp/Meta token": r"EAA[A-Za-z0-9]{50,}",
    "Password in chiaro": r"(?i)(?:password|passwd|pwd|db_pass(?:word)?)\s*[:=]\s*['\"]?[^\s'\"$;{}]{4,}",
    "Secret/API key generica": r"(?i)(?:api[_-]?key|secret|token|auth)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]",
    "Stringa connessione DB": r"(?i)(?:mysql|postgres(?:ql)?|mongodb(?:\+srv)?)://[^\s:'\"]+:[^\s@'\"]+@",
    "IP privato/server": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}
RE = {k: re.compile(v) for k, v in PATTERN.items()}
IP_IGNORA = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "1.1.1.1", "8.8.8.8"}


def maschera(s: str) -> str:
    s = s.strip()
    return s[:4] + "…" + f"({len(s)} car.)" if len(s) > 6 else "****"


def scan_testo(testo: str, origine: str, trovati: list):
    for i, riga in enumerate(testo.splitlines(), 1):
        if len(riga) > 2000:
            continue
        for tipo, rx in RE.items():
            for m in rx.finditer(riga):
                v = m.group(0)
                if tipo == "IP privato/server":
                    parts = v.split(".")
                    if v in IP_IGNORA or any(int(p) > 255 for p in parts) or riga.lstrip().startswith(("version", "\"version")):
                        continue
                trovati.append((origine, i, tipo, maschera(v)))


def scan_file(base: Path, trovati: list):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SALTA]
        for f in filenames:
            p = Path(dirpath, f)
            if p.suffix.lower() in EST_BINARIE:
                continue
            try:
                if p.stat().st_size > 2_000_000:
                    continue
                scan_testo(p.read_text(encoding="utf-8", errors="ignore"), str(p.relative_to(base)), trovati)
            except OSError:
                pass


def scan_storia(base: Path, trovati: list):
    if not (base / ".git").exists():
        return
    out = subprocess.run(["git", "-C", str(base), "log", "-p", "--all", "--no-color"],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    aggiunte = "\n".join(l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++"))
    scan_testo(aggiunte, "[cronologia git]", trovati)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    base = Path(sys.argv[1]).resolve()
    trovati: list = []
    scan_file(base, trovati)
    if "--storia" in sys.argv:
        scan_storia(base, trovati)
    critici = [t for t in trovati if t[2] != "IP privato/server"]
    righe = [f"# Scansione segreti — {base.name}", "",
             f"Data: {datetime.now():%Y-%m-%d %H:%M} · Cartella: `{base}`", "",
             f"**Segreti potenziali: {len(critici)}** · IP trovati: {len(trovati) - len(critici)}", "",
             "| File | Riga | Tipo | Anteprima (mascherata) |", "|---|---|---|---|"]
    righe += [f"| {o} | {r} | {t} | `{m}` |" for o, r, t, m in trovati[:500]]
    out = ROOT / "reports" / f"segreti-{base.name}.md"
    out.write_text("\n".join(righe) + "\n", encoding="utf-8")
    stato = "STOP — segreti trovati, non pubblicare" if critici else "nessun segreto evidente"
    print(f"{base.name}: {stato} ({len(critici)} potenziali, {len(trovati)-len(critici)} IP) → {out.name}")


if __name__ == "__main__":
    main()
