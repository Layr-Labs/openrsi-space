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
        for text, code in (("a" * 3001, "summary-text-too-long"),
                           ("Hidden\u200btext", "disallowed-summary-format"),
                           ("name@example.org", "disallowed-summary-format")):
            value = {"description": text, "distinctive_features": []}
            self.assertIsNone(public_summary(value))
            self.assertEqual(summary_error(value), code)

    def test_layout_normalization_and_multiple_paragraphs(self):
        value = {"description": "  First\r\nwrapped line. \r\n \r\n\r\n Second.\r\r Third.\n ",
                 "distinctive_features": ["  Saves\t checkpoints. "]}
        self.assertEqual(public_summary(value), {"description": "First wrapped line.\n\nSecond.\n\nThird.",
                                                "distinctive_features": ["Saves checkpoints."]})
        for text in ("\x00Safe", "Safe\u200b", "\x1cSafe"):
            self.assertEqual(summary_error({"description": text, "distinctive_features": []}), "disallowed-summary-format")

    def test_character_and_word_boundaries_after_normalization(self):
        for text in ("x"*3000, "word "*250):
            self.assertIsNotNone(public_summary({"description": text, "distinctive_features": []}))
        self.assertEqual(summary_error({"description": "word "*251, "distinctive_features": []}), "summary-too-many-words")
        self.assertIsNotNone(public_summary({"description": "x"*1500, "distinctive_features": []}))
        self.assertIsNotNone(public_summary({"description": "😀"*1501, "distinctive_features": []}))

    def test_unknown_fields_never_leak_into_public_summary(self):
        self.assertIsNone(public_summary({"description": "A research agent.",
            "distinctive_features": [], "private_evidence": "source text"}))


if __name__ == "__main__":
    unittest.main()
