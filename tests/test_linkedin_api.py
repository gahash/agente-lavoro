import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core import config, db, vault
from app.modules import linkedin_api as la
from app.modules import linkedin_post as lp


class LinkedinApiTests(unittest.TestCase):
    def setUp(self):
        tmp = self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for obj, nome, val in ((config, "SETTINGS_FILE", Path(tmp.name) / "s.json"), (db, "DB_PATH", Path(tmp.name) / "t.db"),
                               (lp.linkedin_grafica, "percorso", lambda pid: Path(tmp.name) / f"{pid}.png")):
            p = patch.object(obj, nome, val)
            p.start()
            self.addCleanup(p.stop)
        db.init()
        lp.init()
        self.cred = {"linkedin_token": json.dumps({"token": "T", "scade": time.time() + 9999, "autore": "urn:li:person:abc"})}
        p = patch.object(vault, "get_cred", lambda k: self.cred.get(k))
        p.start()
        self.addCleanup(p.stop)

    def test_testo_little_text(self):
        self.assertEqual(la._testo("Ciao (test) @me\n#AI #Automazione"),
                         "Ciao \\(test\\) \\@me\n{hashtag|\\#|AI} {hashtag|\\#|Automazione}")

    def test_pubblica_carica_immagine_e_segna_pubblicato(self):
        pid = db.x("INSERT INTO post_linkedin (tema, testo, stato, data_prevista) VALUES ('Tema','Testo #AI','approvato','2026-01-01')")
        c = MagicMock()
        c.__enter__.return_value = c
        c.post.side_effect = [MagicMock(json=lambda: {"value": {"uploadUrl": "https://up", "image": "urn:li:image:1"}}),
                              MagicMock(status_code=201, headers={"x-restli-id": "urn:li:share:9"})]
        with patch.object(la.httpx, "Client", return_value=c):
            r = la.pubblica(pid)
        self.assertEqual(r["urn"], "urn:li:share:9")
        corpo = c.post.call_args_list[1].kwargs["json"]
        self.assertEqual(corpo["content"]["media"]["id"], "urn:li:image:1")
        self.assertEqual(corpo["author"], "urn:li:person:abc")
        self.assertTrue(c.put.call_args.kwargs["content"].startswith(b"\x89PNG"))
        self.assertEqual(db.q("SELECT stato FROM post_linkedin WHERE id=?", (pid,))[0]["stato"], "pubblicato")

    def test_senza_collegamento_la_routine_non_fa_nulla(self):
        self.cred = {}
        db.x("INSERT INTO post_linkedin (tema, testo, stato, data_prevista) VALUES ('T','x','approvato','2026-01-01')")
        self.assertEqual(la.pubblica_di_oggi()["pubblicati"], 0)


if __name__ == "__main__":
    unittest.main()
