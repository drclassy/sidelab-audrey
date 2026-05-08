import json
import tempfile
import unittest
from pathlib import Path

from audrey_notify.message_builder import format_referral
import audrey_icd.database as icd_db


class MessageBuilderTests(unittest.TestCase):
    def test_format_referral_without_kriteria_rujuk_does_not_slice_last_character(self):
        response_text = "DIAGNOSIS KERJA:\nA"

        formatted = format_referral(response_text, {}, "ABC123")

        self.assertNotIn("\nA\n\nMohon", formatted)
        self.assertIn("Mohon arahan dan tindak lanjut lebih lanjut dokter.", formatted)


class IcdDatabaseTests(unittest.TestCase):
    def setUp(self):
        self._orig_data_file = icd_db._DATA_FILE
        self._orig_codes_by_key = icd_db._codes_by_key
        self._orig_all_entries = icd_db._all_entries
        self._orig_metadata = icd_db._metadata

    def tearDown(self):
        icd_db._DATA_FILE = self._orig_data_file
        icd_db._codes_by_key = self._orig_codes_by_key
        icd_db._all_entries = self._orig_all_entries
        icd_db._metadata = self._orig_metadata

    def test_metadata_handles_entry_without_code_gracefully(self):
        temp_path = Path(tempfile.gettempdir()) / "icd_bad_fixture.json"
        temp_path.write_text(json.dumps({"codes": [{"name_id": "broken entry"}]}), encoding="utf-8")

        icd_db._DATA_FILE = temp_path
        icd_db._codes_by_key = None
        icd_db._all_entries = None
        icd_db._metadata = None

        meta = icd_db.metadata()

        self.assertEqual(meta.get("invalid_entries"), 1)
        self.assertEqual(icd_db.all_entries(), [{"name_id": "broken entry"}])
        self.assertIsNone(icd_db.get_by_code("I10"))


if __name__ == "__main__":
    unittest.main()
