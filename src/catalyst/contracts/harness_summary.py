"""Bounded public description metadata, independent of validity and scoring."""
import re
import unicodedata


def public_summary(value):
    """Drop malformed metadata rather than changing an evaluation's outcome."""
    if not isinstance(value, dict) or set(value) != {"description", "distinctive_features"}:
        return None

    def prose(text, limit):
        return (isinstance(text, str) and 0 < len(text) <= limit and text == text.strip()
                and not any(unicodedata.category(c).startswith("C") for c in text)
                and not re.search(r"[<>`]|https?://|\bwww\.|\S+@\S+", text, re.I))

    features = value["distinctive_features"]
    if (not prose(value["description"], 600) or not isinstance(features, list)
            or len(features) > 3 or any(not prose(item, 160) for item in features)):
        return None
    return {"description": value["description"], "distinctive_features": list(features)}
