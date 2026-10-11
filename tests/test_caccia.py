import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config
from app.modules import caccia


class CacciaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = patch.object(config, "SETTINGS_FILE", Path(tmp.name) / "s.json")
        p.start()
        self.addCleanup(p.stop)

    def test_interesse(self):
        self.assertEqual(8, caccia._interesse("ottimo candidato [interesse 8/10]"))
        self.assertEqual(5, caccia._interesse("senza punteggio"))

    def test_giro_rispetta_soglia_e_tetti(self):
        aziende = [{"id": 1, "analisi": "x [interesse 9/10]"}, {"id": 2, "analisi": "y [interesse 3/10]"},
                   {"id": 3, "analisi": "z [interesse 7/10]"}]

        def q(sql, params=()):
            if "COUNT(*) n FROM eventi" in sql or "COUNT(*) n FROM bozze" in sql:
                return [{"n": 0}]
            if "stato='Nuovo' AND opt_out=0" in sql:
                return []
            if "stato='Analizzata'" in sql:
                return aziende
            if "FROM opportunita" in sql:
                return [{"id": 10}]
            raise AssertionError(sql)

        config.save_settings({"caccia_solo_analisi": False})
        with patch.object(caccia.db, "q", side_effect=q), patch.object(caccia.db, "log"), \
             patch.object(caccia.pmi, "cerca_osm", return_value={"nuove": 4}), \
             patch.object(caccia.safety, "pmi_quota_residua", return_value=1), \
             patch.object(caccia.bozze, "proposta_pmi", return_value={"ok": True}) as prop, \
             patch.object(caccia.bozze, "candidatura", return_value={"ok": True}):
            r = caccia.giro()
        self.assertEqual(4, r["nuove_aziende"])
        self.assertEqual(1, r["proposte"])                 # quota anti-spam = 1
        prop.assert_called_once_with(1)                    # la più interessante, mai quella a 3/10
        self.assertEqual(1, r["candidature"])


if __name__ == "__main__":
    unittest.main()


class SoloAnalisiTests(unittest.TestCase):
    def test_non_scrive_bozze(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "SETTINGS_FILE", Path(tmp) / "s.json"):
            config.save_settings({"caccia_solo_analisi": True})
            q = lambda sql, params=(): [{"n": 0}] if "COUNT" in sql else ([{"id": 1}] if "stato='Nuovo'" in sql else [{"nome": "X"}])
            with patch.object(caccia.db, "q", side_effect=q), patch.object(caccia.db, "log"), \
                 patch.object(caccia.pmi, "cerca_osm", return_value={"nuove": 2}), \
                 patch.object(caccia.pmi, "analizza", return_value={"ok": True}), \
                 patch.object(caccia.bozze, "proposta_pmi") as prop, patch.object(caccia.bozze, "candidatura") as cand:
                r = caccia.giro()
        self.assertEqual(1, r["analizzate"])
        prop.assert_not_called()
        cand.assert_not_called()
