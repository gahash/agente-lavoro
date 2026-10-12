import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app.core import config
from app.modules import agenda, bozze


class _SettingsTemporanee(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        p = patch.object(config, "SETTINGS_FILE", Path(self._tmp.name) / "impostazioni.json")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)


class RipetizioniTests(unittest.TestCase):
    def test_toglie_la_frase_quasi_uguale(self):
        corpo = ("Ho integrato LLM in un progetto precedente. "
                 "Sono disponibile a discutere ulteriormente la mia candidatura e come possa contribuire al successo di Mitre Media. "
                 "Sono pronto a ricevere una chiamata per discutere ulteriormente la mia candidatura e come possa contribuire al successo di Mitre Media.")
        testo, tolte = bozze.togli_ripetizioni(corpo)
        self.assertEqual(1, len(tolte))
        self.assertIn("Sono disponibile", testo)
        self.assertNotIn("Sono pronto", testo)

    def test_lascia_stare_le_frasi_diverse_e_i_paragrafi(self):
        corpo = "Buongiorno,\n\nHo visto il vostro sito e la chat WhatsApp attiva.\n\nPropongo una demo di 20 minuti senza impegno."
        testo, tolte = bozze.togli_ripetizioni(corpo)
        self.assertEqual([], tolte)
        self.assertEqual(corpo, testo)


class FollowUpTests(_SettingsTemporanee):
    def _follow(self, ultimo):
        pipe = {"id": 1, "solleciti": 0, "ultimo_contatto": ultimo, "contatto": "a@b.it", "azienda": "TEST Srl"}
        with patch.object(bozze.db, "q", return_value=[pipe]), \
             patch.object(bozze, "_salva", return_value=7) as salva, \
             patch.object(agenda, "slot_liberi", return_value=[datetime(2026, 10, 13, 16, 30)]):
            bozze.follow_up(1)
        return salva.call_args.args[3]

    def test_senza_data_non_lascia_il_buco(self):
        corpo = self._follow(None)
        self.assertIn("riprendo il mio messaggio precedente nel caso", corpo)
        self.assertNotIn("del  ", corpo)

    def test_con_data_e_orari_liberi(self):
        corpo = self._follow("2026-10-07T22:38:00")
        self.assertIn("messaggio del 07/10/2026", corpo)
        self.assertIn("- martedì 13/10 alle 16:30", corpo)
        self.assertIn("prenota.php", corpo)


class SlotTests(_SettingsTemporanee):
    ADESSO = datetime(2026, 10, 11, 20, 0)          # domenica sera

    def test_mai_nelle_ore_di_riunione_e_un_orario_per_giorno(self):
        slot = agenda.slot_liberi(3, esistenti=[], adesso=self.ADESSO)
        self.assertEqual([datetime(2026, 10, 12, 16, 30), datetime(2026, 10, 13, 16, 30), datetime(2026, 10, 14, 16, 30)], slot)

    def test_salta_gli_orari_gia_presi_nel_gestionale(self):
        presi = [{"inizio": "2026-10-12 16:15:00", "fine": "2026-10-12 17:00:00"}]
        self.assertEqual(datetime(2026, 10, 12, 17, 15), agenda.slot_liberi(1, esistenti=presi, adesso=self.ADESSO)[0])

    def test_ore_occupate_e_spazi_liberi(self):
        self.assertTrue(agenda._occupato(datetime(2026, 10, 12, 10, 0), 30))
        self.assertFalse(agenda._occupato(datetime(2026, 10, 12, 11, 0), 20))
        self.assertTrue(agenda._occupato(datetime(2026, 10, 12, 13, 40), 30))   # sfora lo spazio libero
        self.assertFalse(agenda._occupato(datetime(2026, 10, 12, 16, 0), 30))
        self.assertFalse(agenda._occupato(datetime(2026, 10, 17, 10, 0), 30))   # sabato

    def test_crea_rifiuta_le_ore_occupate_senza_chiamare_il_sito(self):
        with patch.object(agenda, "_chiama") as chiama:
            r = agenda.crea("Call", "2026-10-12 10:00")
        self.assertFalse(r["ok"])
        chiama.assert_not_called()



class RifinituraTests(unittest.TestCase):
    def test_corregge_gli_errori_ricorrenti(self):
        c = bozze.rifinisci("Buongiorno,\n\nHo visto una chatbot e una demo di 2 a 20 minuti per i dei client: ok")
        self.assertEqual("Buongiorno,\n\nho visto un chatbot e una demo di 20 minuti per i dei clienti: ok", c)

    def test_segnala_le_promesse_rischiose(self):
        p = bozze.promesse_rischiose("Demo gratuita, senza costi iniziali. Posso iniziare lunedì prossimo.")
        self.assertEqual(["gratuit", "lunedì prossim", "senza costi"], p)
        self.assertEqual([], bozze.promesse_rischiose("Una demo di 20 minuti, senza impegno."))


if __name__ == "__main__":
    unittest.main()
