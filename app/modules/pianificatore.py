"""Routine automatiche mentre l'app è aperta: posta, ricerca lavoro, report.
Le routine preparano solo dati e bozze: non inviano mai nulla."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from ..core import db
from ..core.config import load_settings
from . import attivita, lavoro, posta, report

sched = BackgroundScheduler(timezone="Europe/Rome")


def _safe(nome, fn, *a, **kw):
    def run():
        try:
            fn(*a, **kw)
        except Exception as e:
            db.log("pianificatore", f"{nome}: {e}", "errore")
    return run


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def portali_routine() -> None:
    """Se attivato: importa annunci da LinkedIn/Indeed per le prime 2 ricerche, solo se già collegati."""
    s = load_settings()
    if not s.get("portali_auto"):
        return
    from . import portali
    import random
    import time
    from . import browser
    collegati = portali.stato()
    if collegati.pop("gestionale", False):
        _safe("crm", browser.leggi_tabelle, s["crm_url_lead"])()
    for p, ok_ in collegati.items():
        if not ok_:
            continue
        for parole in s["ricerche_portali"][:2]:
            _safe("portali", portali.cerca_e_importa, p, parole)()
            time.sleep(random.uniform(20, 45))          # ritmo umano tra una ricerca e l'altra


def avvia() -> None:
    s = load_settings()
    sched.remove_all_jobs()
    for i, ora in enumerate(s["controllo_posta"]):
        h, m = _hm(ora)
        sched.add_job(_safe("posta", posta.controlla), "cron", hour=h, minute=m, id=f"posta{i}")
    h, m = _hm(s["ricerca_lavoro_ora"])
    sched.add_job(_safe("lavoro", lavoro.cerca), "cron", hour=h, minute=m, id="lavoro")
    hp, mp = divmod(h * 60 + m + 20, 60)
    sched.add_job(_safe("portali", portali_routine), "cron", day_of_week="mon-fri", hour=hp % 24, minute=mp,
                  id="portali")
    h, m = _hm(s["report_mattino"])
    sched.add_job(_safe("report", report.report, "mattino"), "cron", hour=h, minute=m, id="rep_m")
    h, m = _hm(s["report_sera"])
    sched.add_job(_safe("report", report.report, "sera"), "cron", hour=h, minute=m, id="rep_s")
    sched.add_job(_safe("report", report.report, "settimanale"), "cron", day_of_week="fri", hour=17, id="rep_w")
    sched.add_job(_safe("attivita", attivita.genera), "cron", hour=7, minute=0, id="attivita")
    if not sched.running:
        sched.start()


def recupero_avvio() -> None:
    """All'apertura dell'app esegue le attività di oggi non ancora fatte (in background)."""
    import threading
    from datetime import date, datetime

    from ..core import vault
    from ..core.config import REPORTS

    def job():
        oggi = date.today().isoformat()
        fatto = lambda mod, testo: db.q("SELECT 1 FROM eventi WHERE modulo=? AND quando LIKE ? AND messaggio LIKE ?",
                                        (mod, oggi + "%", testo + "%"))
        db.log("pianificatore", "Avvio: recupero attività di oggi")
        if vault.get_cred("imap_password"):
            _safe("posta", posta.controlla)()
        if not fatto("lavoro", "Ricerca"):
            _safe("lavoro", lavoro.cerca, max_ai=5)()
            portali_routine()
        tipo = "sera" if datetime.now().hour >= 18 else "mattino"
        if not (REPORTS / f"{oggi}_{tipo}.md").exists():
            _safe("report", report.report, tipo)()
        _safe("attivita", attivita.genera)()
        db.log("pianificatore", "Avvio: attività completate")

    threading.Thread(target=job, daemon=True, name="recupero").start()


def stato() -> list[dict]:
    return [{"id": j.id, "prossima": j.next_run_time.strftime("%d/%m %H:%M") if j.next_run_time else ""}
            for j in sched.get_jobs()]
