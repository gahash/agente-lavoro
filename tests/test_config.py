import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import config


class SettingsTests(unittest.TestCase):
    def test_load_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "impostazioni.json"
            settings_file.write_text("{", encoding="utf-8")

            with patch.object(config, "SETTINGS_FILE", settings_file):
                with self.assertRaisesRegex(config.SettingsError, "Impossibile leggere"):
                    config.load_settings()

    def test_load_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "impostazioni.json"
            settings_file.write_text("[]", encoding="utf-8")

            with patch.object(config, "SETTINGS_FILE", settings_file):
                with self.assertRaisesRegex(config.SettingsError, "oggetto JSON"):
                    config.load_settings()

    def test_save_keeps_known_settings_and_ignores_unknown_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "impostazioni.json"

            with patch.object(config, "SETTINGS_FILE", settings_file):
                saved = config.save_settings({"max_pmi_giorno": 10, "non_prevista": True})

            on_disk = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(10, saved["max_pmi_giorno"])
            self.assertEqual(10, on_disk["max_pmi_giorno"])
            self.assertNotIn("non_prevista", on_disk)
            self.assertEqual([], list(settings_file.parent.glob(".impostazioni.json.*")))

    def test_save_removes_temporary_file_if_serialization_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "impostazioni.json"

            with patch.object(config, "SETTINGS_FILE", settings_file):
                with self.assertRaisesRegex(config.SettingsError, "Impossibile salvare"):
                    config.save_settings({"nome": object()})

            self.assertFalse(settings_file.exists())
            self.assertEqual([], list(settings_file.parent.glob(".impostazioni.json.*")))


if __name__ == "__main__":
    unittest.main()
