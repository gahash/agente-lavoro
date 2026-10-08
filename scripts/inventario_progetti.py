"""Inventario progetti sul PC (SOLA LETTURA).

Scansiona le cartelle indicate in config.yaml (inventario.radici), riconosce i
progetti dai file "marcatore" (package.json, composer.json, .git, ...), ne
deduce lo stack e propone una classificazione A/B/C/D da confermare a mano.

Non apre file sensibili: segnala solo per NOME i file a rischio (.env, *.sql,
*.pem, credenziali...). Output: data/inventario-progetti.csv e .md
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

MARCATORI = {
    "package.json": "Node/JS",
    "composer.json": "PHP",
    "artisan": "Laravel",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "manage.py": "Django",
    "pubspec.yaml": "Flutter",
    "build.gradle": "Android/Gradle",
    "build.gradle.kts": "Android/Gradle",
    "platformio.ini": "PlatformIO/IoT",
    "app.json": "Expo/React Native",
    "docker-compose.yml": "Docker",
    "Dockerfile": "Docker",
    "wp-config.php": "WordPress",
    "index.php": "PHP",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
}
SALTA = {"node_modules", ".git", "vendor", ".venv", "venv", "__pycache__", "dist",
         "build", ".next", ".expo", "android", "ios", ".gradle", "storage", "cache"}
RISCHIO_NOMI = (".env", "credentials", "credenziali", "secret", "password", "id_rsa",
                "serviceaccount", "service-account", "config.php", "wp-config.php")
RISCHIO_EST = (".sql", ".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".sqlite", ".db", ".bak", ".dump")
PAROLE_A = ("whatsapp", "agent", "agente", "crm", "assistente", "voice", "vocale", "omnichannel",
            "platform", "piattaforma", "saas", "ai")
PAROLE_B = ("fattura", "gestional", "pharma", "farmac", "ecommerce", "shop", "cliente", "webagency")


def git_info(p: Path) -> dict:
    if not (p / ".git").exists():
        return {"git": "no", "remote": "", "ultimo_commit": "", "commit": ""}
    def run(*a):
        try:
            return subprocess.run(["git", "-C", str(p), *a], capture_output=True, text=True,
                                  timeout=15).stdout.strip()
        except Exception:
            return ""
    return {"git": "si", "remote": run("remote", "get-url", "origin"),
            "ultimo_commit": run("log", "-1", "--format=%cs"),
            "commit": run("rev-list", "--count", "HEAD")}


def analizza(p: Path, max_file=40000) -> dict:
    stack, rischi, n, ultima, dim = set(), [], 0, 0.0, 0
    for dirpath, dirnames, filenames in os.walk(p):
        dirnames[:] = [d for d in dirnames if d not in SALTA]
        for f in filenames:
            n += 1
            if n > max_file:
                break
            fp = Path(dirpath, f)
            if f in MARCATORI:
                stack.add(MARCATORI[f])
            low = f.lower()
            if low.endswith(RISCHIO_EST) or any(k in low for k in RISCHIO_NOMI):
                if not low.endswith((".example", ".sample", ".dist")):
                    rischi.append(str(fp.relative_to(p)))
            try:
                st = fp.stat()
                dim += st.st_size
                ultima = max(ultima, st.st_mtime)
            except OSError:
                pass
    # dipendenze chiave da package.json / composer.json (sola lettura, file non sensibili)
    for nome in ("package.json", "composer.json"):
        f = p / nome
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
                deps = {**d.get("dependencies", {}), **d.get("require", {})}
                for k, lab in (("react", "React"), ("next", "Next.js"), ("vue", "Vue"), ("express", "Express"),
                               ("laravel/framework", "Laravel"), ("whatsapp-web.js", "WhatsApp"),
                               ("@whiskeysockets/baileys", "WhatsApp"), ("openai", "OpenAI"),
                               ("twilio", "Twilio"), ("expo", "Expo"),
                               ("electron", "Electron"), ("mysql2", "MySQL"), ("mongoose", "MongoDB"),
                               ("pg", "PostgreSQL"), ("socket.io", "Socket.io")):
                    if k in deps:
                        stack.add(lab)
            except Exception:
                pass
    return {"stack": ", ".join(sorted(stack)), "file": n, "mb": round(dim / 1e6, 1),
            "modificato": datetime.fromtimestamp(ultima).strftime("%Y-%m-%d") if ultima else "",
            "file_a_rischio": len(rischi), "esempi_rischio": "; ".join(rischi[:5])}


def proponi_categoria(nome: str, stack: str) -> str:
    n = nome.lower()
    if any(k in n for k in PAROLE_B):
        return "B? (cliente)"
    if any(k in n for k in PAROLE_A) or "WhatsApp" in stack:
        return "A? (prodotto)"
    return "C? (da valutare)"


def main():
    righe = []
    for radice in CFG["inventario"]["radici"]:
        r = Path(os.path.expandvars(os.path.expanduser(radice)))
        if not r.exists():
            continue
        for p in sorted(x for x in r.iterdir() if x.is_dir() and not x.name.startswith(".")):
            if p.resolve() == ROOT:
                continue
            a = analizza(p)
            if a["file"] == 0:
                continue
            riga = {"progetto": p.name, "percorso": str(p), **git_info(p), **a}
            riga["categoria_proposta"] = proponi_categoria(p.name, a["stack"])
            riga["categoria_confermata"] = ""
            righe.append(riga)
            print(f"  • {p.name:30} {riga['categoria_proposta']:18} {a['stack']}", file=sys.stderr)
    if not righe:
        print("Nessun progetto trovato.")
        return
    out = ROOT / "data" / "inventario-progetti.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(righe[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(righe)
    md = ["# Inventario progetti (generato " + datetime.now().strftime("%Y-%m-%d %H:%M") + ")", "",
          "> Classificazione **proposta** in automatico: va confermata da Gaspare progetto per progetto.", "",
          "| Progetto | Stack | Git / remote | Ultima modifica | File a rischio | Categoria proposta |",
          "|---|---|---|---|---|---|"]
    for r in righe:
        git = r["git"] + (f" · {r['remote']}" if r["remote"] else "")
        md.append(f"| {r['progetto']} | {r['stack'] or '—'} | {git} | {r['modificato']} | "
                  f"{r['file_a_rischio']} | {r['categoria_proposta']} |")
    (ROOT / "data" / "inventario-progetti.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"OK: {len(righe)} progetti → data/inventario-progetti.csv / .md")


if __name__ == "__main__":
    main()
