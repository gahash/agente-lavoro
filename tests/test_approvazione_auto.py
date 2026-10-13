import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config, db
from app.modules import bozze

BUONA = ("Buongiorno,\n\nho visitato il sito della Trattoria e ho notato che per prenotare i clienti devono ancora "
         "telefonare negli orari di apertura del locale.\n\nLe propongo un assistente AI su WhatsApp che risponde alle "
         "domande ricorrenti e raccoglie le prenotazioni anche quando il locale è chiuso.\n\nSe Le interessa, posso "
         "mostrarLe come funzionerebbe con una demo di 20 minuti, senza impegno.\n\nUn saluto,\nGaspare Pettinati")


class ApprovazioneAutomaticaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for obj, nome, val in ((config, "SETTINGS_FILE", Path(tmp.name) / "s.json"), (db, "DB_PATH", Path(tmp.name) / "t.db")):
            p = patch.object(obj, nome, val)
            p.start()
            self.addCleanup(p.stop)
        db.init()

    def _stato(self, tipo="proposta_pmi", dest="info@trattoria.it", ogg="Prenotazioni su WhatsApp", corpo=BUONA):
        bid = bozze._salva(tipo, dest, ogg, corpo, "aziende", 1)
        return db.q("SELECT stato, note FROM bozze WHERE id=?", (bid,))[0]

    def test_proposta_pulita_approvata_da_sola(self):
        r = self._stato()
        self.assertEqual("approvata", r["stato"])
        self.assertIn("approvata in automatico", r["note"])

    def test_proposte_con_problemi_restano_da_rivedere(self):
        casi = {
            "promesse": BUONA.replace("senza impegno", "gratuita e senza costi"),
            "tu": BUONA.replace("Le propongo", "Ti propongo").replace("Se Le interessa", "Se ti interessa"),
            "corta": "Buongiorno,\n\nLe propongo un chatbot.",
        }
        for nome, corpo in casi.items():
            with self.subTest(nome):
                self.assertEqual("da_approvare", self._stato(corpo=corpo)["stato"])
        self.assertEqual("da_approvare", self._stato(dest="")["stato"])
        self.assertEqual("da_approvare", self._stato(tipo="linkedin")["stato"])

    def test_candidature_con_email_approvate_da_sole(self):
        self.assertEqual("approvata", self._stato(tipo="candidatura", dest="jobs@azienda.com", ogg="Candidatura Senior AI Engineer")["stato"])
        self.assertEqual("da_approvare", self._stato(tipo="candidatura", dest="", ogg="Candidatura Senior AI Engineer")["stato"])

    def test_disattivabile_e_con_tetto_giornaliero(self):
        config.save_settings({"auto_max_giorno": 2})
        stati = [self._stato()["stato"] for _ in range(3)]
        self.assertEqual(["approvata", "approvata", "da_approvare"], stati)
        config.save_settings({"approvazione_automatica": False})
        self.assertEqual("da_approvare", self._stato()["stato"])


if __name__ == "__main__":
    unittest.main()
