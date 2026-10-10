import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import api


class FileAccessTests(unittest.TestCase):
    def test_allows_an_existing_file_inside_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "dati"
            data.mkdir()
            report = data / "report.txt"
            report.write_text("ok", encoding="utf-8")

            with patch.object(api, "DATA", data):
                response = api.apri_file(str(report))

            self.assertEqual(report.resolve(), Path(response.path))

    def test_rejects_sibling_directory_with_same_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "dati"
            sibling = Path(tmp) / "dati-esterna"
            data.mkdir()
            sibling.mkdir()
            outside = sibling / "privato.txt"
            outside.write_text("segreto", encoding="utf-8")

            with patch.object(api, "DATA", data):
                with self.assertRaises(HTTPException) as raised:
                    api.apri_file(str(outside))

            self.assertEqual(403, raised.exception.status_code)

    def test_rejects_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "dati"
            data.mkdir()

            with patch.object(api, "DATA", data):
                with self.assertRaises(HTTPException) as raised:
                    api.apri_file(str(data / "assente.txt"))

            self.assertEqual(404, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
