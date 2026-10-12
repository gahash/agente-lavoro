import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

from app.core import config, db
from app.modules import linkedin_post as lp


class LinkedinPostTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for obj, nome, val in ((config, "SETTINGS_FILE", Path(tmp.name) / "s.json"), (db, "DB_PATH", Path(tmp.name) / "t.db")):
            p = patch.object(obj, nome, val)
            p.start()
            self.addCleanup(p.stop)
        db.init()

    def test_serie_iniziale_almeno_10_post_validi_una_volta_sola(self):
        self.assertGreaterEqual(lp.crea_serie_iniziale(), 10)
        self.assertEqual(0, lp.crea_serie_iniziale())
        post = lp.lista()
        self.assertGreaterEqual(len(post), 10)
        for p in post:
            self.assertLessEqual(len(p["testo"]), lp.LIMITE)
            self.assertIn("#", p["testo"])
            self.assertIn(date.fromisoformat(p["data_prevista"]).weekday(), (1, 3))
        self.assertEqual(len(post), len({p["data_prevista"] for p in post}))

    def test_approvazione_pubblicazione_e_link(self):
        lp.crea_serie_iniziale()
        pid = lp.lista()[0]["id"]
        self.assertFalse(lp.aggiorna(pid, {"stato": "boh"})["ok"])
        self.assertFalse(lp.aggiorna(pid, {"testo": "x" * 3001})["ok"])
        lp.aggiorna(pid, {"stato": "approvato", "data_prevista": "2000-01-01"})
        self.assertEqual([pid], [p["id"] for p in lp.di_oggi()])
        url = lp.link_pubblica(pid)
        self.assertTrue(url.startswith("https://www.linkedin.com/feed/?shareActive=true&text="))
        self.assertIn("L'intelligenza artificiale", unquote(url))
        lp.aggiorna(pid, {"stato": "pubblicato"})
        self.assertEqual([], lp.di_oggi())

    def test_genera_finisce_in_bozza_nella_prima_data_libera(self):
        lp.crea_serie_iniziale()
        with patch.object(lp.llm, "chat", return_value="Gancio.\n\nTesto del post.\n\n#AI"):
            r = lp.genera("Errori nei progetti AI")
        nuovo = [p for p in lp.lista() if p["id"] == r["id"]][0]
        self.assertEqual("bozza", nuovo["stato"])
        self.assertNotIn(nuovo["data_prevista"], {p["data_prevista"] for p in lp.lista() if p["id"] != r["id"]})


if __name__ == "__main__":
    unittest.main()
