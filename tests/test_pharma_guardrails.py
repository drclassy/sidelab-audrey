import unittest

import medgemma_chat as m


class PharmaGuardrailTests(unittest.TestCase):
    def test_noninfectious_msk_filters_irrelevant_antibiotics_and_backfills_rational_options(self):
        response = """DIAGNOSIS KERJA:
M19.9 Osteoartritis

FARMAKOLOGI:
Paracetamol 3x500mg PO 5 hari PC
Amoxicilin-Klavulanat 625 mg PO 3x1 5 hari PC
Metronidazol 1x500 mg PO 5 hari PC

EDUKASI PASIEN:
-"""

        formatted = m._format_farmakologi_tree(response)

        self.assertIn("Paracetamol 3x500mg PO 5 hari PC", formatted)
        self.assertNotIn("Amoxicilin-Klavulanat", formatted)
        self.assertNotIn("Metronidazol", formatted)
        self.assertIn("Ibuprofen 3x400 mg PO 5 hari PC", formatted)
        self.assertIn("Vitamin B kompleks 1x1 PO 5 hari PC", formatted)


if __name__ == "__main__":
    unittest.main()
