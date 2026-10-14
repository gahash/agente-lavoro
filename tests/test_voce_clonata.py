import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core import config, db, vault
from app.modules import video_brevi as vb
from app.modules import voce_clonata as vc


def _tono(dest: Path, secondi: float = 4) -> None:
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / 16000)))
                                for i in range(int(16000 * secondi))))


class VoceClonataTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for obj, nome, val in ((config, "SETTINGS_FILE", self.dir / "s.json"), (db, "DB_PATH", self.dir / "t.db"),
                               (vb, "CARTELLA", self.dir / "video"), (vc, "CAMPIONI", self.dir / "campioni")):
            p = patch.object(obj, nome, val)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(vault, "get_cred", lambda k: "chiave" if k == "elevenlabs_api_key" else None)
        p.start()
        self.addCleanup(p.stop)
        db.init()
        vb.init()

    def test_campioni_e_creazione_voce(self):
        src = self.dir / "x.tmp"
        src.write_bytes(b"audio")
        self.assertTrue(vc.aggiungi_campione(src, "Nuova registrazione.m4a")["ok"])
        self.assertFalse(vc.aggiungi_campione(self.dir / "y.tmp", "foto.jpg")["ok"])
        with patch.object(vc.httpx, "post", return_value=MagicMock(status_code=200, json=lambda: {"voice_id": "v1"})) as post:
            self.assertEqual("v1", vc.crea_voce()["voce_id"])
        self.assertEqual("chiave", post.call_args.kwargs["headers"]["xi-api-key"])
        self.assertEqual(1, len(post.call_args.kwargs["files"]))
        self.assertEqual("v1", config.load_settings()["elevenlabs_voce_id"])

    def test_video_letto_con_la_voce_clonata(self):
        config.save_settings({"elevenlabs_voce_id": "v1"})
        vid = db.x("INSERT INTO video_brevi (tema, copione, testo) VALUES ('T','Prima frase.\nSeconda frase.','x')")

        def finto_leggi(testo, dest):
            self.assertIn("Seconda frase.", testo)
            self.assertIn(vb.CHIUSURA, testo)
            dest.parent.mkdir(parents=True, exist_ok=True)
            _tono(dest)
            return dest
        with patch.object(vc, "leggi", side_effect=finto_leggi):
            r = vb.voce_automatica(vid)
        self.assertTrue(r["ok"], r)
        self.assertTrue(vb.voce_path(vid).exists())


if __name__ == "__main__":
    unittest.main()
