"""Bounded public description metadata, independent of validity and scoring."""
import re
import unicodedata


DESCRIPTION_LIMIT = 1400


def summary_error(value):
    """Fixed diagnostic codes; never return generated text or source evidence."""
    if not isinstance(value, dict) or set(value) != {"description", "distinctive_features"}:
        return "invalid-summary-shape"

    def prose(text, limit, *, paragraphs=False):
        if not isinstance(text, str) or not text or text != text.strip():
            return "invalid-summary-text"
        if len(text) > limit:
            return "summary-text-too-long"
        parts = text.split("\n\n") if paragraphs else [text]
        if len(parts) > 2 or any(not part or part != part.strip() for part in parts):
            return "invalid-summary-paragraphs"
        plain = " ".join(parts)
        if (any(unicodedata.category(c).startswith("C") for c in plain)
                or re.search(r"[<>`]|https?://|\bwww\.|\S+@\S+", plain, re.I)):
            return "disallowed-summary-format"
        return None

    features = value["distinctive_features"]
    if not isinstance(features, list) or len(features) > 3:
        return "invalid-summary-features"
    error = prose(value["description"], DESCRIPTION_LIMIT, paragraphs=True)
    if error:
        return error
    for feature in features:
        error = prose(feature, 160)
        if error:
            return error
    return None


def public_summary(value):
    """Drop malformed metadata rather than changing an evaluation's outcome."""
    if summary_error(value) is not None:
        return None
    return {"description": value["description"], "distinctive_features": list(value["distinctive_features"])}
