"""Publication choices carried with each new evaluation request."""
from .common import CatalystError

SOURCE_LICENSES = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "GPL-3.0-only",
    "GPL-3.0-or-later", "AGPL-3.0-only", "MPL-2.0", "CC0-1.0", "CC-BY-4.0",
})


def publication_choices(value=None):
    """Source is public by default; traces are retained only for internal use."""
    if value is None:
        value = {"harness": True, "traces": False, "license": None}
    if (not isinstance(value, dict) or set(value) != {"harness", "traces", "license"}
            or type(value["harness"]) is not bool or value["traces"] is not False
            or (value["license"] is not None and (
                not isinstance(value["license"], str) or value["license"] not in SOURCE_LICENSES))
            or (not value["harness"] and value["license"] is not None)):
        raise CatalystError(
            "Choose public or private harness source and an optional supported source license. "
            "Traces are retained internally and cannot be downloaded or published.")
    return dict(value)
