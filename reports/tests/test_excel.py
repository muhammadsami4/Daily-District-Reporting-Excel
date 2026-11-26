import io
import unittest
from datetime import date

from openpyxl import load_workbook

from reports.core.constants import CATEGORIES, COLUMN_WIDTHS, DISTRICTS
from reports.core.excel import build_workbook, read_sheet_values, workbook_to_bytes
from .helpers import REFERENCE, grid_rows, parse, sample

CATS = [(c["code"], c["excel_header"]) for c in CATEGORIES]


def export(text, report_date, **kw):
    p = parse(text)
    return workbook_to_bytes(build_workbook(report_date, grid_rows(p), CATS, **kw))


class ReferenceComparisonTests(unittest.TestCase):
    """The example text for 25-11-2026 must reproduce the reference workbook exactly."""

    @classmethod
    def setUpClass(cls):
        cls.data = export(sample("example_valid.txt"), date(2026, 11, 25))
        cls.mine = read_sheet_values(io.BytesIO(cls.data))
        cls.ref = read_sheet_values(REFERENCE)

    def test_every_cell_equals_reference(self):
        self.assertEqual(self.mine, self.ref)

    def test_dimensions_and_districts(self):
        self.assertEqual(len(self.mine), 39)                                   # header + 38
        self.assertEqual([r[1] for r in self.mine[1:]], [n for n, _ in DISTRICTS])
        self.assertEqual([r[0] for r in self.mine[1:]], list(range(1, 39)))

    def test_column_totals_match_declared(self):
        totals = [sum(r[i] for r in self.mine[1:]) for i in range(3, 9)]
        self.assertEqual(totals, [23, 2, 0, 28, 0, 0])

    def test_formatting_matches_reference(self):
        ws, ref = load_workbook(io.BytesIO(self.data)).active, load_workbook(REFERENCE).active
        self.assertEqual(ws.title, ref.title)
        for col in "ABCDEFGHI":
            h, rh = ws[f"{col}1"], ref[f"{col}1"]
            self.assertTrue(h.font.b)
            self.assertEqual(h.fill.fgColor.rgb, rh.fill.fgColor.rgb)
            self.assertEqual(h.font.color.rgb, rh.font.color.rgb)
            self.assertEqual(h.alignment.horizontal, "center")
        for col, width in COLUMN_WIDTHS.items():
            self.assertAlmostEqual(ws.column_dimensions[col].width, ref.column_dimensions[col].width, places=3)
        self.assertEqual(ws["C2"].number_format, ref["C2"].number_format)
        self.assertIsInstance(ws["C2"].value, str)                              # text date like the reference


class ExportSafetyTests(unittest.TestCase):
    def test_refuses_negative_missing_or_text_values(self):
        for bad in (-1, None, "3", 2.5):
            with self.assertRaises(ValueError):
                build_workbook(date(2026, 1, 1), [("Lahore", {"added": bad})], CATS)

    def test_refuses_duplicate_districts(self):
        with self.assertRaises(ValueError):
            build_workbook(date(2026, 1, 1), [("Lahore", {}), ("Lahore", {})], CATS)

    def test_zero_districts_included(self):
        mine = read_sheet_values(io.BytesIO(export("24-11-2026\nLocated Total: 0", date(2026, 11, 24))))
        self.assertEqual(len(mine), 39)
        self.assertTrue(all(v == 0 for r in mine[1:] for v in r[3:]))

    def test_optional_totals_row_uses_formulas(self):
        ws = load_workbook(io.BytesIO(export(sample("example_valid.txt"), date(2026, 11, 24),
                                             include_totals_row=True))).active
        self.assertEqual(ws["D40"].value, "=SUM(D2:D39)")


if __name__ == "__main__":
    unittest.main()
