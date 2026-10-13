import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.core import config, db
from app.modules import linkedin_post as lp


class LinkedinPostTests(unittest.TestCase):
    def setUp(self):
        tmp = self._tmp = tempfile.TemporaryDirectory()
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
        self.assertEqual(lp.link_pubblica(), "https://www.linkedin.com/feed/?shareActive=true")
        lp.aggiorna(pid, {"stato": "pubblicato"})
        self.assertEqual([], lp.di_oggi())

    def test_genera_finisce_in_bozza_nella_prima_data_libera(self):
        lp.crea_serie_iniziale()
        with patch.object(lp.llm, "chat", return_value="Gancio.\n\nTesto del post.\n\n#AI"):
            r = lp.genera("Errori nei progetti AI")
        nuovo = [p for p in lp.lista() if p["id"] == r["id"]][0]
        self.assertEqual("bozza", nuovo["stato"])
        self.assertNotIn(nuovo["data_prevista"], {p["data_prevista"] for p in lp.lista() if p["id"] != r["id"]})

    def test_ogni_post_ha_la_sua_grafica(self):
        from PIL import Image
        from app.modules import linkedin_grafica as lg
        with patch.object(lg, "CARTELLA", Path(self._tmp.name) / "li"):
            lp.crea_serie_iniziale()
            for p in lp.lista():
                with Image.open(lp.grafica(p["id"])) as img:
                    self.assertEqual((1200, 1200), img.size)


class ContenutoGraficaTests(unittest.TestCase):
    def test_intestazioni_degli_elenchi_e_maiuscole(self):
        from app.modules.linkedin_grafica import contenuto
        titolo, voci = contenuto("Titolo forte.\n\nCloud quando:\n• dati non sensibili\n\nLocale quando:\n• dati sanitari\n\n#AI")
        self.assertEqual("Titolo forte.", titolo)
        self.assertEqual([("intestazione", "Cloud quando:"), ("punto", "Dati non sensibili"),
                          ("intestazione", "Locale quando:"), ("punto", "Dati sanitari")], voci)

    def test_al_massimo_cinque_punti(self):
        from app.modules.linkedin_grafica import contenuto
        _, voci = contenuto("T\n" + "\n".join(f"{i}. punto {i}" for i in range(1, 8)))
        self.assertEqual(5, len(voci))


if __name__ == "__main__":
    unittest.main()
