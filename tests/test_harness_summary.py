"""Public summaries preserve readable prose while excluding unsafe metadata."""
import unittest
from catalyst.contracts.harness_summary import public_summary, summary_error


class HarnessSummaryTests(unittest.TestCase):
    def test_legacy_and_long_two_paragraph_text(self):
        for description in ("A stock research agent.", "First paragraph. " * 45 + "Ends here.\n\nSecond paragraph."):
            value = {"description": description, "distinctive_features": []}
            self.assertEqual(public_summary(value), value)
            self.assertIsNone(summary_error(value))

    def test_only_description_accepts_paragraph_breaks(self):
        value = {"description": "First.\n\nSecond.", "distinctive_features": ["First.\n\nSecond."]}
        self.assertIsNone(public_summary(value))

    def test_invalid_text_is_omitted_with_fixed_diagnostic(self):
        for text, code in (("a" * 1401, "summary-text-too-long"),
                           ("One.\n\nTwo.\n\nThree.", "invalid-summary-paragraphs"),
                           ("One.\nTwo.", "disallowed-summary-format"),
                           ("Hidden\u200btext", "disallowed-summary-format"),
                           ("name@example.org", "disallowed-summary-format")):
            value = {"description": text, "distinctive_features": []}
            self.assertIsNone(public_summary(value))
            self.assertEqual(summary_error(value), code)

    def test_unknown_fields_never_leak_into_public_summary(self):
        self.assertIsNone(public_summary({"description": "A research agent.",
            "distinctive_features": [], "private_evidence": "source text"}))


if __name__ == "__main__":
    unittest.main()
