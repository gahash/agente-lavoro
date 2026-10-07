"""Database SQLite locale."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from .config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunita (
  id INTEGER PRIMARY KEY, fonte TEXT, uid TEXT UNIQUE, azienda TEXT, ruolo TEXT, link TEXT,
  tipo TEXT, remoto TEXT, compenso TEXT, requisiti TEXT, contatto TEXT, descrizione TEXT,
  punteggio REAL, motivazione TEXT, sospetto INTEGER DEFAULT 0, stato TEXT DEFAULT 'Nuovo',
  creato TEXT, aggiornato TEXT);

CREATE TABLE IF NOT EXISTS aziende (
  id INTEGER PRIMARY KEY, uid TEXT UNIQUE, nome TEXT, settore TEXT, citta TEXT, sito TEXT,
  email TEXT, telefono TEXT, fonte_dato TEXT, analisi TEXT, servizio TEXT,
  stato TEXT DEFAULT 'Nuovo', opt_out INTEGER DEFAULT 0, creato TEXT, aggiornato TEXT);

CREATE TABLE IF NOT EXISTS bozze (
  id INTEGER PRIMARY KEY, tipo TEXT, destinatario TEXT, oggetto TEXT, corpo TEXT,
  rif_tabella TEXT, rif_id INTEGER, in_risposta_a TEXT, stato TEXT DEFAULT 'da_approvare',
  note TEXT, creato TEXT, aggiornato TEXT, inviato TEXT);

CREATE TABLE IF NOT EXISTS posta (
  id INTEGER PRIMARY KEY, uid TEXT UNIQUE, message_id TEXT, mittente TEXT, oggetto TEXT,
  data TEXT, anteprima TEXT, categoria TEXT, motivo TEXT, allarme TEXT, gestita INTEGER DEFAULT 0,
  creato TEXT);

CREATE TABLE IF NOT EXISTS pipeline (
  id INTEGER PRIMARY KEY, tipo TEXT, azienda TEXT, contatto TEXT, canale TEXT, stato TEXT,
  primo_contatto TEXT, ultimo_contatto TEXT, prossimo_passo TEXT, data_prossimo TEXT,
  valore REAL, fonte TEXT, link TEXT, note TEXT, solleciti INTEGER DEFAULT 0, creato TEXT, aggiornato TEXT);

CREATE TABLE IF NOT EXISTS registro_contatti (
  id INTEGER PRIMARY KEY, data TEXT, azienda TEXT, referente TEXT, fonte_dato TEXT,
  base_giuridica TEXT, canale TEXT, rif_bozza INTEGER, opt_out INTEGER DEFAULT 0, data_opt_out TEXT, note TEXT);

CREATE TABLE IF NOT EXISTS lead_crm (
  id INTEGER PRIMARY KEY, uid TEXT UNIQUE, dati TEXT, letto TEXT);

CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY, ruolo TEXT, testo TEXT, quando TEXT);

CREATE TABLE IF NOT EXISTS attivita (
  id INTEGER PRIMARY KEY, uid TEXT UNIQUE, data TEXT, ora TEXT, titolo TEXT, dettaglio TEXT,
  origine TEXT, vista TEXT, priorita INTEGER DEFAULT 2, fatto INTEGER DEFAULT 0, fatto_il TEXT);

CREATE TABLE IF NOT EXISTS eventi (
  id INTEGER PRIMARY KEY, quando TEXT, livello TEXT, modulo TEXT, messaggio TEXT);
"""


CON_DATA = {"opportunita", "aziende", "bozze", "posta", "pipeline"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, conn() as c:
        c.executescript(SCHEMA)


def q(sql: str, params: tuple | list = ()) -> list[dict]:
    with _lock, conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def x(sql: str, params: tuple | list = ()) -> int:
    with _lock, conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid or cur.rowcount


def insert(table: str, data: dict, ignore: bool = True) -> int | None:
    data = {**data}
    if table in CON_DATA:
        data.setdefault("creato", now())
    cols = ",".join(data)
    qs = ",".join("?" * len(data))
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    with _lock, conn() as c:
        cur = c.execute(f"{verb} INTO {table} ({cols}) VALUES ({qs})", list(data.values()))
        return cur.lastrowid if cur.rowcount else None


def update(table: str, id_: int, data: dict) -> None:
    if table in CON_DATA and table != "posta":
        data = {**data, "aggiornato": now()}
    sets = ",".join(f"{k}=?" for k in data)
    x(f"UPDATE {table} SET {sets} WHERE id=?", [*data.values(), id_])


def log(modulo: str, messaggio: str, livello: str = "info") -> None:
    try:
        x("INSERT INTO eventi (quando, livello, modulo, messaggio) VALUES (?,?,?,?)",
          (now(), livello, modulo, messaggio[:2000]))
    except Exception:
        pass


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)
