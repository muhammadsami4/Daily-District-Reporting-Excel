import unittest
from datetime import date

from reports.core.parser import ERROR
from .helpers import codes, parse, sample


class ExampleInputTests(unittest.TestCase):
    def setUp(self):
        self.p = parse(sample("example_valid.txt"))

    def test_date(self):
        self.assertEqual(self.p.report_date, date(2026, 11, 24))

    def test_declared_totals(self):
        self.assertEqual(self.p.declared, {"added": 23, "released": 2, "deported": 0,
                                           "under_process": 28, "returned": None, "arrested_lea": 0})

    def test_district_values(self):
        self.assertEqual(self.p.entries["added"], {"Rawalpindi": 1, "Chakwal": 5, "Gujranwala": 17})
        self.assertEqual(self.p.entries["released"], {"Attock": 2})          # '02' -> 2
        self.assertEqual(self.p.entries["under_process"], {"Attock": 7, "Gujrat": 19, "Toba Tek Singh": 2})
        self.assertEqual(self.p.entries["deported"], {})

    def test_no_errors(self):
        self.assertFalse([i for i in self.p.issues if i.level == ERROR])

    def test_missing_category_reported_as_info_only(self):
        self.assertIn("category_not_supplied", codes(self.p.issues))   # 'returned' not supplied


class FormattingToleranceTests(unittest.TestCase):
    def test_messy_input_gives_same_result_as_clean(self):
        clean, messy = parse(sample("example_valid.txt")), parse(sample("example_messy_but_valid.txt"))
        self.assertEqual(clean.entries, messy.entries)
        self.assertEqual(clean.declared, messy.declared)
        self.assertEqual(clean.report_date, messy.report_date)
        self.assertFalse([i for i in messy.issues if i.level == ERROR])

    def test_district_spelling_variants(self):
        for variant in ["T.T.Singh", "T.T. Singh", "Toba Tek Singh", "toba tek singh", "TT Singh", "t.t.singh."]:
            p = parse(f"01-01-2026\nLocated Total: 4\n{variant}: 4")
            self.assertEqual(p.entries["added"], {"Toba Tek Singh": 4}, variant)

    def test_category_variants(self):
        for variant in ["UnderProcess", "Under Process", "under process", "UNDERPROCESS"]:
            p = parse(f"01-01-2026\n{variant}: 3\nLahore: 3")
            self.assertEqual(p.entries["under_process"], {"Lahore": 3}, variant)
            self.assertEqual(p.declared["under_process"], 3)

    def test_trailing_fullstop_and_case(self):
        p = parse("01-01-2026\nLocated Total: 3\nChakwal.: 1\nrawalpindi: 2.")
        self.assertEqual(p.entries["added"], {"Chakwal": 1, "Rawalpindi": 2})

    def test_murree_reference_spelling(self):
        p = parse("01-01-2026\nLocated Total: 2\nMurree: 1\nMuree: ")
        # 'Muree' without a number is a missing value, not silently zero
        self.assertIn("duplicate_entry", codes(p.issues))


class ProblemDetectionTests(unittest.TestCase):
    def setUp(self):
        self.p = parse(sample("example_invalid_duplicate_unknown.txt"))

    def test_duplicate_district_leaves_cell_blank_not_guessed(self):
        self.assertIn("duplicate_entry", codes(self.p.issues))
        self.assertIsNone(self.p.entries["added"]["Chakwal"])

    def test_unknown_district_is_unresolved_not_dropped(self):
        self.assertEqual([(u.raw_name, u.value, u.category) for u in self.p.unresolved],
                         [("Atlantis", 5, "added")])

    def test_negative_district_value_blank(self):
        self.assertIn("negative_value", codes(self.p.issues))
        self.assertIsNone(self.p.entries["under_process"]["Lahore"])

    def test_negative_total_is_sticky_error(self):
        issue = next(i for i in self.p.issues if i.code == "negative_total")
        self.assertTrue(issue.sticky)


class DateTests(unittest.TestCase):
    def test_missing_date(self):
        p = parse("Located Total: 1\nLahore: 1")
        self.assertIsNone(p.report_date)
        self.assertIn("missing_date", codes(p.issues))

    def test_form_date_used_when_text_has_none(self):
        p = parse("Located Total: 1\nLahore: 1", form_date=date(2026, 1, 5))
        self.assertEqual(p.report_date, date(2026, 1, 5))

    def test_mismatch(self):
        p = parse(sample("example_valid.txt"), form_date=date(2026, 11, 25))
        self.assertIsNone(p.report_date)
        self.assertIn("date_mismatch", codes(p.issues))

    def test_invalid_calendar_date(self):
        p = parse("31-02-2026\nLocated Total: 1\nLahore: 1")
        self.assertIsNone(p.report_date)
        self.assertIn("invalid_date", codes(p.issues))

    def test_multiple_dates(self):
        p = parse("24-11-2026\n25-11-2026\nLocated Total: 1\nLahore: 1")
        self.assertIn("multiple_dates", codes(p.issues))


class StructureTests(unittest.TestCase):
    def test_value_before_category(self):
        p = parse("24-11-2026\nLahore: 3\nLocated Total: 3")
        self.assertIn("value_outside_category", codes(p.issues))

    def test_duplicate_category(self):
        p = parse("24-11-2026\nLocated Total: 1\nLahore: 1\nLocated Total: 2\nKasur: 2")
        self.assertIn("duplicate_category", codes(p.issues))

    def test_no_categories(self):
        self.assertIn("no_categories", codes(parse("24-11-2026\n\n").issues))

    def test_fuzzy_match_is_flagged_never_silent(self):
        p = parse("24-11-2026\nLocated Total: 1\nFaislabad: 1")
        self.assertEqual(p.entries["added"], {"Faisalabad": 1})
        self.assertIn("fuzzy_district", codes(p.issues))

    def test_garbage_name_not_guessed(self):
        p = parse("24-11-2026\nLocated Total: 1\nXyzabc: 1")
        self.assertEqual(p.entries["added"], {})
        self.assertEqual(len(p.unresolved), 1)

    def test_digits_in_name_not_fuzzy_matched(self):
        p = parse("24-11-2026\nLocated Total: 3\nChakwal 5 3")
        self.assertEqual(p.entries["added"], {})
        self.assertEqual(len(p.unresolved), 1)

    def test_district_without_number_flagged(self):
        p = parse("24-11-2026\nLocated Total: 1\nLahore")
        self.assertIn("missing_value", codes(p.issues))
        self.assertIsNone(p.entries["added"]["Lahore"])

    def test_commentary_line_ignored_with_warning(self):
        p = parse("24-11-2026\nDaily report\nLocated Total: 1\nLahore: 1")
        self.assertIn("ignored_line", codes(p.issues))


if __name__ == "__main__":
    unittest.main()
