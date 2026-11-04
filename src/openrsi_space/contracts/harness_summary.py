"""Bounded public description metadata, independent of validity and scoring."""
import re
import unicodedata

DESCRIPTION_LIMIT = 3000
DESCRIPTION_WORD_LIMIT = 250
RAW_TEXT_LIMIT = 60000


def normalize_prose(text):
    """Normalize layout only; leave unsafe characters for validation to reject."""
    if not isinstance(text, str) or len(text) > RAW_TEXT_LIMIT:
        return text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraphs, current = [], []
    for line in lines:
        line = re.sub(r"[ \t]+", " ", line).strip(" ")
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def normalized(value):
    return {"description": normalize_prose(value["description"]),
            "distinctive_features": [normalize_prose(v) for v in value["distinctive_features"]]}


def summary_error(value):
    """Fixed diagnostic codes; never return generated text or source evidence."""
    if not isinstance(value, dict) or set(value) != {"description", "distinctive_features"}:
        return "invalid-summary-shape"
    features = value["distinctive_features"]
    if not isinstance(features, list) or len(features) > 3:
        return "invalid-summary-features"

    def prose(raw, limit, *, paragraphs=False):
        if not isinstance(raw, str):
            return "invalid-summary-text"
        if len(raw) > RAW_TEXT_LIMIT:
            return "summary-text-too-long"
        # Formatting normalization must not erase hidden/control characters.
        if any(unicodedata.category(c).startswith("C") and c not in "\r\n\t" for c in raw):
            return "disallowed-summary-format"
        text = normalize_prose(raw)
        if not text:
            return "invalid-summary-text"
        if len(text) > limit:
            return "summary-text-too-long"
        if paragraphs and len(text.split()) > DESCRIPTION_WORD_LIMIT:
            return "summary-too-many-words"
        plain = text.replace("\n\n", " ") if paragraphs else text
        if (any(unicodedata.category(c).startswith("C") for c in plain)
                or re.search(r"[<>`]|https?://|\bwww\.|\S+@\S+", plain, re.I)):
            return "disallowed-summary-format"
        return None

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
    return normalized(value)
