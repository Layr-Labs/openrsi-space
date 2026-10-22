"""Format-neutral catalogs for immutable, operator-supplied task resources."""
import hashlib
import re

from catalyst.common import CatalystError, canonical

NAME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
MEDIA_TYPE = r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*"


def write_resource_catalog(destination, library, resources, slug, release):
    """Validate local bytes and publish a catalog; this performs no downloads."""
    if (not isinstance(slug, str) or not re.fullmatch(NAME, slug)
            or not isinstance(release, str) or not re.fullmatch(NAME, release)):
        raise CatalystError("Invalid problem slug or release tag.")
    prefix = f"/{slug}/{release}"
    entries, attachments, ids, names = [], [], set(), set()
    for resource in resources:
        identity, name = resource.get("id", ""), resource.get("filename", "")
        if (not isinstance(identity, str) or not re.fullmatch(NAME, identity) or identity in ids
                or not isinstance(name, str) or not re.fullmatch(NAME, name) or name in names
                or name in {"resources.json", "description.json", "knowledge-base.json"}
                or not isinstance(resource.get("kind"), str) or not resource["kind"]
                or not isinstance(resource.get("title"), str) or not resource["title"]
                or not isinstance(resource.get("media_type"), str)
                or not re.fullmatch(MEDIA_TYPE, resource["media_type"])):
            raise CatalystError("Invalid or duplicate knowledge-base resource.")
        path = destination / name
        if (destination.is_symlink() or path.is_symlink() or not path.is_file()
                or type(resource.get("bytes")) is not int or not 0 < resource["bytes"] <= 32 * 1024 * 1024
                or path.stat().st_size != resource["bytes"]):
            raise CatalystError("Missing or changed knowledge-base resource.")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != resource.get("sha256"):
                raise CatalystError("Knowledge-base resource digest mismatch.")
        paths = [f"{prefix}/resources/{identity}", f"/{slug}/resources/{identity}"]
        entries.append({**resource, "url": "http://gateway:8080" + paths[0]})
        attachments.append({"name": name, "resource_id": identity, "paths": paths,
                            **{key: resource[key] for key in ("bytes", "sha256", "media_type")}})
        ids.add(identity)
        names.add(name)
    metadata = {key: value for key, value in library.items() if key not in {"papers", "resources", "count"}}
    raw = canonical({**metadata, "schema_version": 1, "id": library["id"], "title": library.get("title", library["id"]),
                     "release": release, "count": len(entries), "resources": entries})
    (destination / "resources.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    attachments.append({"name": "resources.json", "bytes": len(raw), "sha256": digest,
                        "media_type": "application/json",
                        "paths": [prefix + "/knowledge-base", f"/{slug}/knowledge-base"]})
    return {"id": library["id"], "count": len(entries), "sha256": digest,
            "url": "http://gateway:8080" + prefix + "/knowledge-base"}, attachments
