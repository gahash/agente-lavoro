import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.modules import pmi

HTML = ("<html><body><h1>Trattoria Da Mario</h1><p>" + "Cucina tipica bergamasca, menu del giorno e specialità. " * 10 +
        "</p><p>Per prenotare chiamate il 035 123456.</p><a href='https://instagram.com/mario'>IG</a>"
        "<a href='https://wa.me/39333'>WhatsApp</a></body></html>")
AZ = {"id": 1, "nome": "Da Mario", "settore": "Ristoranti", "citta": "Bergamo", "sito": "https://mario.it",
      "email": "info@mario.it", "servizio": pmi.SERVIZI_AI[0], "stato": "Nuovo"}


class AnalisiAITests(unittest.TestCase):
    def _analizza(self, html, risposta):
        with patch.object(pmi, "_scarica", return_value=(html, BeautifulSoup(html, "html.parser"))), \
             patch.object(pmi.db, "q", return_value=[AZ]), patch.object(pmi.db, "update") as upd, \
             patch.object(pmi.safety, "email_in_opt_out", return_value=False), \
             patch.object(pmi.llm, "chat_json", return_value=risposta) as chat:
            r = pmi.analizza(1)
        return r, upd.call_args.args[2], chat

    def test_sceglie_il_servizio_ai_dall_elenco_e_salva_il_caso_d_uso(self):
        r, campi, chat = self._analizza(HTML, {"cosa_manca": "prenotazione online", "servizio": 1,
                                               "caso_uso": "risponde al telefono e prende le prenotazioni", "interesse": 9})
        self.assertTrue(r["ok"])
        self.assertEqual(pmi.SERVIZI_AI[0], campi["servizio"])
        self.assertIn("Caso d'uso AI: risponde al telefono", campi["analisi"])
        self.assertIn("[interesse 9/10]", campi["analisi"])
        segnali = chat.call_args.args[1]
        self.assertIn("ha: WhatsApp, social", segnali)
        self.assertIn("prenotazione online", segnali.split("manca:")[1])

    def test_sito_illeggibile_scartato_senza_ai(self):
        r, campi, chat = self._analizza("<html><body>Enable JavaScript</body></html>", {})
        self.assertFalse(r["ok"])
        self.assertEqual("Scartato", campi["stato"])
        chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
