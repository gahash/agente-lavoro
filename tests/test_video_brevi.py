import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core import config, db
from app.modules import linkedin_api as la
from app.modules import video_brevi as vb


class VideoBreviTests(unittest.TestCase):
    def setUp(self):
        tmp = self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for obj, nome, val in ((config, "SETTINGS_FILE", Path(tmp.name) / "s.json"), (db, "DB_PATH", Path(tmp.name) / "t.db"),
                               (vb, "CARTELLA", Path(tmp.name) / "video")):
            p = patch.object(obj, nome, val)
            p.start()
            self.addCleanup(p.stop)
        db.init()
        vb.init()
        config.save_settings({"video_voce": ""})          # senza voce: test veloce e indipendente dal Mac

    def test_serie_iniziale_una_volta_nei_giorni_previsti(self):
        self.assertEqual(len(vb.SERIE_INIZIALE), vb.crea_serie_iniziale())
        self.assertEqual(0, vb.crea_serie_iniziale())
        from datetime import date
        self.assertTrue(all(date.fromisoformat(v["data_prevista"]).weekday() in (2, 4) for v in vb.lista()))

    def test_monta_un_mp4(self):
        vid = db.x("INSERT INTO video_brevi (tema, copione, testo) VALUES ('Prova','Prima frase.\nSeconda frase.','x')")
        f = vb.monta(vid)
        self.assertGreater(f.stat().st_size, 10_000)
        self.assertEqual(b"ftyp", f.read_bytes()[4:8])
        vb.aggiorna(vid, {"copione": "Altra frase."})        # copione cambiato: il video va rifatto
        self.assertFalse(f.exists())

    def test_pubblica_video_a_pezzi_e_dopo_elaborazione(self):
        vid = db.x("INSERT INTO video_brevi (tema, copione, testo, stato) VALUES ('T','x','Testo #AI','approvato')")
        dati = b"0123456789"
        c = MagicMock()
        c.__enter__.return_value = c
        c.post.side_effect = [
            MagicMock(json=lambda: {"value": {"video": "urn:li:video:1", "uploadToken": "tk", "uploadInstructions": [
                {"uploadUrl": "u1", "firstByte": 0, "lastByte": 4}, {"uploadUrl": "u2", "firstByte": 5, "lastByte": 9}]}}),
            MagicMock(), MagicMock(status_code=201, headers={"x-restli-id": "urn:li:share:5"})]
        c.put.side_effect = [MagicMock(headers={"etag": '"e1"'}), MagicMock(headers={"etag": '"e2"'})]
        c.get.side_effect = [MagicMock(json=lambda: {"status": "PROCESSING"}), MagicMock(json=lambda: {"status": "AVAILABLE"})]
        with patch.object(vb, "monta", return_value=MagicMock(read_bytes=lambda: dati)), \
             patch.object(la, "_sessione", return_value=({"autore": "urn:li:person:a"}, {"Authorization": "Bearer T"})), \
             patch.object(la.httpx, "Client", return_value=c), patch.object(la.time, "sleep"):
            r = la.pubblica_video(vid)
        self.assertEqual("urn:li:share:5", r["urn"])
        self.assertEqual([b"01234", b"56789"], [k.kwargs["content"] for k in c.put.call_args_list])
        fin = c.post.call_args_list[1].kwargs["json"]["finalizeUploadRequest"]
        self.assertEqual(["e1", "e2"], fin["uploadedPartIds"])
        self.assertEqual("urn:li:video:1", c.post.call_args_list[2].kwargs["json"]["content"]["media"]["id"])
        self.assertEqual("pubblicato", db.q("SELECT stato FROM video_brevi WHERE id=?", (vid,))[0]["stato"])


    def test_carica_mov_convertito_in_mp4_e_separato_dai_video_brevi(self):
        vid = db.x("INSERT INTO video_brevi (tema, copione, testo) VALUES ('Prova','Una frase abbastanza lunga.','x')")
        mp4 = vb.monta(vid)
        sorgente = mp4.parent / "registrazione.tmp"
        sorgente.write_bytes(mp4.read_bytes())
        r = vb.carica(sorgente, "Il mio video.mov")
        self.assertTrue(r["ok"], r)
        f = vb.monta(r["id"])
        self.assertEqual(".mp4", f.suffix)
        self.assertEqual(b"ftyp", f.read_bytes()[4:8])
        self.assertEqual([r["id"]], [v["id"] for v in vb.lista(caricati=True)])
        self.assertNotIn(r["id"], [v["id"] for v in vb.lista()])
        self.assertFalse(vb.carica(mp4.parent / "x.tmp", "foto.jpg")["ok"])


if __name__ == "__main__":
    unittest.main()
