import unittest
from datetime import date

from reports.core.constants import CATEGORIES, DISTRICTS
from reports.core.parser import ERROR, WARNING
from reports.core.validator import has_errors, validate_grid
from .helpers import CODES, parse, sample

LABELS = {c["code"]: c["label"] for c in CATEGORIES}
NAMES = {str(i): n for i, (n, _) in enumerate(DISTRICTS)}
KEY = {n: k for k, n in NAMES.items()}


def grid_from(parsed):
    g = {k: {c: 0 for c in CODES} for k in NAMES}
    for c, per in parsed.entries.items():
        for n, v in per.items():
            g[KEY[n]][c] = v
    return g


def run(parsed, **kw):
    return validate_grid(parsed.report_date, grid_from(parsed), parsed.declared, LABELS, NAMES,
                         today=date(2026, 11, 30), **kw)


class ValidatorTests(unittest.TestCase):
    def test_example_is_valid(self):
        issues = run(parse(sample("example_valid.txt")))
        self.assertFalse(has_errors(issues), [i.message for i in issues])

    def test_total_mismatch_detected_and_nothing_adjusted(self):
        p = parse(sample("example_invalid_total.txt"))
        issues = run(p)
        mismatch = [i for i in issues if i.code == "total_mismatch"]
        self.assertEqual(len(mismatch), 1)
        self.assertIn("declared total is 24", mismatch[0].message)
        self.assertIn("add up to 23", mismatch[0].message)
        self.assertEqual(p.declared["added"], 24)                       # untouched
        self.assertEqual(sum(p.entries["added"].values()), 23)

    def test_missing_cell_blocks(self):
        p = parse("24-11-2026\nLocated Total: 2\nLahore: 1\nLahore: 1")
        self.assertTrue(has_errors(run(p)))

    def test_invalid_and_negative_cells(self):
        g = {"0": {c: 0 for c in CODES}}
        g["0"]["added"], g["0"]["released"] = "abc", -2
        issues = validate_grid(date(2026, 1, 1), g, {}, LABELS, NAMES)
        self.assertEqual({i.code for i in issues}, {"invalid_number", "negative_value"})

    def test_missing_date(self):
        issues = validate_grid(None, {"0": {c: 0 for c in CODES}}, {}, LABELS, NAMES)
        self.assertEqual([i.code for i in issues], ["missing_date"])

    def test_future_date_is_warning(self):
        issues = validate_grid(date(2027, 1, 1), {"0": {c: 0 for c in CODES}}, {}, LABELS, NAMES,
                               today=date(2026, 11, 30))
        self.assertEqual([(i.code, i.level) for i in issues], [("future_date", WARNING)])

    def test_no_declared_total_is_warning(self):
        g = {"0": {c: 0 for c in CODES}}
        g["0"]["returned"] = 3
        issues = validate_grid(date(2026, 1, 1), g, {"returned": None}, LABELS, NAMES)
        self.assertEqual([(i.code, i.level) for i in issues], [("no_declared_total", WARNING)])

    def test_unconfirmed_mapping_blocks_only_when_figures_present(self):
        g = {"0": {c: 0 for c in CODES}}
        self.assertFalse(has_errors(validate_grid(date(2026, 1, 1), g, {}, LABELS, NAMES,
                                                  unconfirmed=["arrested_lea"])))
        g["0"]["arrested_lea"] = 1
        issues = validate_grid(date(2026, 1, 1), g, {"arrested_lea": 1}, LABELS, NAMES,
                               unconfirmed=["arrested_lea"])
        self.assertEqual([i.code for i in issues if i.level == ERROR], ["mapping_unconfirmed"])


if __name__ == "__main__":
    unittest.main()
