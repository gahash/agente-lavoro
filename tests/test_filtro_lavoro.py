import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config
from app.modules import lavoro


class FiltroTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = patch.object(config, "SETTINGS_FILE", Path(tmp.name) / "s.json")
        p.start()
        self.addCleanup(p.stop)

    def ok(self, **o):
        return lavoro.ammesso(o)[0]

    def test_remoto_aperto_all_italia(self):
        self.assertTrue(self.ok(ruolo="Backend dev", remoto="Sì (mondo)"))
        self.assertTrue(self.ok(ruolo="Backend dev", remoto="Sì (Italia · Milano)"))
        self.assertTrue(self.ok(ruolo="Backend dev", remoto="Sì (100%)"))

    def test_esclusi(self):
        self.assertFalse(self.ok(ruolo="Backend dev", remoto="No (Milano)"))
        self.assertFalse(self.ok(ruolo="Backend dev", remoto="Ibrido (Roma)"))
        self.assertFalse(self.ok(ruolo="Backend dev", remoto="Sì (USA)"))
        self.assertFalse(self.ok(ruolo="Backend dev", remoto="Sì (mondo)", descrizione="Must be based in the US"))
        self.assertFalse(self.ok(ruolo="Backend dev", remoto=""))

    def test_collaborazioni_sempre_ammesse(self):
        self.assertTrue(self.ok(ruolo="Sviluppatore Python freelance", remoto="No (Milano)"))
        self.assertTrue(self.ok(ruolo="Dev", tipo="Contract", remoto=""))
        self.assertTrue(self.ok(ruolo="Dev", descrizione="Collaborazione con partita IVA", remoto="No (Torino)"))

    def test_collaborazione_da_remoto_riservata_ad_altri_paesi(self):
        self.assertFalse(self.ok(ruolo="Python Team Lead", tipo="Contractor", remoto="Sì (Bulgaria)"))
        self.assertFalse(self.ok(ruolo="AI Trainer", tipo="contract", remoto="Sì (USA, UK, India)"))


    def test_annuncio_hacker_news_con_email_offuscata(self):
        c = {"id": 7, "text": "Acme AI | Senior Python Engineer | REMOTE (Europe) | Full-time | €80k<p>Write to jobs [at] acme [dot] ai"}
        a = lavoro._annuncio_hn(c)
        self.assertEqual(("Acme AI", "Senior Python Engineer", "jobs@acme.ai", "Sì (Europe)", "€80k"),
                         (a["azienda"], a["ruolo"], a["contatto"], a["remoto"], a["compenso"]))
        self.assertTrue(self.ok(**{k: a[k] for k in ("ruolo", "tipo", "remoto", "descrizione")}))
        self.assertIsNone(lavoro._annuncio_hn({"id": 8, "text": "Acme | Engineer | Onsite NYC<p>jobs@acme.ai"}))
        self.assertIsNone(lavoro._annuncio_hn({"id": 9, "text": "Acme | Engineer | REMOTE<p>apply on our site"}))
        self.assertIsNone(lavoro._annuncio_hn({"id": 10, "text": "Acme | Engineer | Remote US<p>jobs@acme.ai"}))


if __name__ == "__main__":
    unittest.main()
