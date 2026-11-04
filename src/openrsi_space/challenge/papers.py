"""Content-pinned task papers, prepared before agent execution."""
from openrsi_space.compatibility import environment as _environment
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.parse import urlsplit

from openrsi_space.common import OpenRSIError, canonical

from .paths import PROBLEM_DIRECTORIES

CATALOG = PROBLEM_DIRECTORIES["ecdsa.fail"] / "knowledge-base/v1.json"
CATALOGS = {"ecdsa-papers-v1": CATALOG}
BUNDLED_PAPERS = CATALOG.parent / "bundled"
LIBRARY_URL = "http://gateway:8080/task/files/knowledge-base.json"
MAX_PAPER_BYTES = 32 * 1024 * 1024
PAPER_HOSTS = {"arxiv.org", "export.arxiv.org", "eprint.iacr.org"}


def validate_download_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in PAPER_HOSTS
            or parsed.username is not None or parsed.password is not None
            or parsed.port is not None or parsed.query or parsed.fragment):
        raise OpenRSIError("Paper downloads require a trusted arXiv or IACR HTTPS URL.")


class PaperRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_catalog(binding):
    path = CATALOGS.get(binding.get("id")) if isinstance(binding, dict) else None
    if path is None:
        raise OpenRSIError("The problem's paper library does not match an installed catalog.")
    raw = path.read_bytes()
    document = json.loads(raw)
    if (binding != {"id": document["id"], "sha256": hashlib.sha256(canonical(document)).hexdigest()}
            or type(document.get("count")) is not int
            or not 0 < document["count"] <= 50
            or len(document.get("papers", [])) != document["count"]):
        raise OpenRSIError("The problem's paper library does not match the installed catalog.")
    names = set()
    for paper in document["papers"]:
        name = paper["file"]
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,123}\.pdf", name) or name in names
                or type(paper["bytes"]) is not int or not 0 < paper["bytes"] <= MAX_PAPER_BYTES
                or not re.fullmatch(r"[0-9a-f]{64}", paper["sha256"])):
            raise OpenRSIError("Invalid paper catalog entry.")
        names.add(name)
        validate_download_url(paper["pdf_url"])
    return document


def matches(path, paper):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != paper["bytes"]:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == paper["sha256"]


def cached_paper(paper, cache):
    path = cache / paper["file"]
    if matches(path, paper):
        return path
    # Pinned, licensed copies keep upstream download restrictions from blocking
    # preparation. They carry the same attribution as downloaded copies.
    bundled = BUNDLED_PAPERS / paper["file"]
    if bundled.exists() or bundled.is_symlink():
        if not matches(bundled, paper):
            raise OpenRSIError(f"Bundled task paper {paper['id']} does not match its pinned SHA-256.")
        return bundled
    cache.mkdir(parents=True, exist_ok=True)
    validate_download_url(paper["pdf_url"])
    opener = build_opener(ProxyHandler({}), PaperRedirect())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as target:
            temporary = Path(target.name)
            with opener.open(Request(paper["pdf_url"], headers={
                    "User-Agent": "OpenRSIResearchLibrary/1.0"}), timeout=90) as response:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > paper["bytes"]:
                        raise OpenRSIError("Paper download exceeds its pinned size.")
                    target.write(chunk)
        if not matches(temporary, paper):
            raise OpenRSIError("Paper download does not match its pinned SHA-256.")
        temporary.chmod(0o644)
        os.replace(temporary, path)
    except Exception as error:
        raise OpenRSIError(f"Unable to prepare task paper {paper['id']}: {error}") from error
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return path


def prepare_library(binding, destination, *, slug=None, release=None):
    """Only operator-selected, pinned catalog entries may become task files."""
    catalog = load_catalog(binding)
    cache = Path(_environment("OPENRSI_PAPER_CACHE",
                                str(Path.home() / ".cache/openrsi/papers")))
    destination.mkdir(parents=True)
    papers = []
    attachments = []
    for paper in catalog["papers"]:
        source = cached_paper(paper, cache)
        shutil.copyfile(source, destination / paper["file"])
        papers.append({**paper, "url": "http://gateway:8080/task/files/" + paper["file"]})
        attachments.append({"name": paper["file"], "sha256": paper["sha256"],
                            "bytes": paper["bytes"], "media_type": "application/pdf"})
    # Attribution and original licenses travel with the raw, unmodified PDFs.
    raw = canonical({**catalog, "papers": papers})
    (destination / "knowledge-base.json").write_bytes(raw)
    attachments.append({"name": "knowledge-base.json", "sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw), "media_type": "application/json"})
    metadata = {"id": catalog["id"], "count": len(papers), "url": LIBRARY_URL}
    if slug is not None:
        from .resources import write_resource_catalog
        resources = [{**{k: v for k, v in paper.items() if k not in {"file", "url"}},
                      "filename": paper["file"], "kind": "paper"} for paper in papers]
        metadata, generic_attachments = write_resource_catalog(destination, catalog, resources, slug, release)
        attachments = [attachments[-1], *generic_attachments]
    for path in destination.iterdir():
        path.chmod(0o644)
    destination.chmod(0o755)
    return metadata, attachments
