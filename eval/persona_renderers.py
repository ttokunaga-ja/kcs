"""Deterministic, dependency-free source renderers for persona-PC fixtures.

The renderer deliberately returns *planned* contract chunks, not observed KIO
chunk hashes.  A later attestation phase is authoritative for actual chunks.
Every function is pure with respect to the host: no clock, randomness, network,
filesystem, locale, or optional package is consulted.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import default as EMAIL_POLICY
import csv
import hashlib
import html
import io
import json
import posixpath
import re
import struct
import unicodedata
import wave
import xml.etree.ElementTree as ET
from zipfile import ZIP_STORED, ZipFile, ZipInfo
import zlib

try:  # Support package imports and direct ``eval/*.py`` script execution.
    from . import persona_fixture_spec as fixture_spec
except ImportError:  # pragma: no cover - exercised by direct-script smoke test
    import persona_fixture_spec as fixture_spec


RENDERER_ID = "kio-persona-renderer"
RENDERER_SCHEMA_VERSION = 1
CHUNKING_MAX_CHARS = 6_000
CODE_LAST_CHUNK_CHARS = 512
MAX_RAW_SOURCE_BYTES = 512 * 1024 * 1024
# The current KIO adapter input ceiling is stricter than the raw-file storage
# contract.  Core fixtures must stay eligible rather than become
# ``skipped_oversized`` before their disposition can be attested.
MAX_ADAPTER_INPUT_BYTES = 100 * 1024 * 1024
MAX_RENDERED_SOURCE_BYTES = min(MAX_RAW_SOURCE_BYTES, MAX_ADAPTER_INPUT_BYTES)
_FIXED_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_SOURCE_ID = re.compile(r"^(p[0-9]{2})-src-[0-9]{6}$")
_SAFE_MEMBER_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,191}$")
_LOGICAL_MEMBER_KINDS = frozenset((
    "document", "message", "attachment", "page", "sheet", "slide",
    "image", "audio", "packet",
))


class RendererContractError(ValueError):
    """Raised before publication when a source cannot satisfy the contract."""


@dataclass(frozen=True)
class SourceRequest:
    schema_version: int
    persona_id: str
    scope_key: str
    source_id: str
    version: int
    family: str
    variant: str
    requested_contributor_chunks: int


@dataclass(frozen=True)
class LogicalMember:
    """Planned logical membership; never evidence of an observed KIO chunk."""

    unit_key: str
    kind: str
    ordinal: int
    label: str
    planned_section_keys: tuple[str, ...]
    planned_contract_chunks: int


@dataclass(frozen=True)
class RenderedSource:
    data: bytes
    extension: str
    media_type: str
    logical_members: tuple[LogicalMember, ...]
    planned_contract_chunks: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


_VARIANT_OUTPUT = {
    "md": ("md", "text/markdown"),
    "markdown": ("markdown", "text/markdown"),
    "txt": ("txt", "text/plain"),
    "log": ("log", "application/octet-stream"),
    "jsonl": ("jsonl", "application/octet-stream"),
    "py": ("py", "text/x-code"),
    "rs": ("rs", "text/x-code"),
    "ts": ("ts", "text/x-code"),
    "json": ("json", "application/octet-stream"),
    "yaml": ("yaml", "application/octet-stream"),
    "xml": ("xml", "application/octet-stream"),
    "sql": ("sql", "application/octet-stream"),
    "csv": ("csv", "application/octet-stream"),
    "tsv": ("tsv", "application/octet-stream"),
    "html": ("html", "application/octet-stream"),
    "eml": ("eml", "application/octet-stream"),
    "ipynb": ("ipynb", "application/octet-stream"),
    "pdf-text": ("pdf", "application/pdf"),
    "pdf-scan": ("pdf", "application/pdf"),
    "docx": (
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "xlsx": (
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "pptx": (
        "pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    "png": ("png", "image/png"),
    "wav": ("wav", "audio/wav"),
    "pcap": ("pcap", "application/vnd.tcpdump.pcap"),
}


def variant_output_contract(family, variant):
    """Return the frozen extension/media-type pair for one valid variant.

    Generators use this before materializing bytes so the immutable source
    plan can be validated without trusting caller-supplied file metadata.
    """
    _variant_policy(family, variant)
    try:
        return _VARIANT_OUTPUT[variant]
    except KeyError as error:  # Defensive if the specification grows first.
        raise RendererContractError(
            f"variant has no safe core renderer: {variant!r}"
        ) from error


def _variant_policy(family, variant):
    if family not in fixture_spec.FORMAT_VARIANTS:
        raise RendererContractError(f"unknown format family: {family!r}")
    for name, _percentage, gate_role, disposition in fixture_spec.FORMAT_VARIANTS[family]:
        if name == variant:
            return gate_role, disposition
    raise RendererContractError(
        f"variant {variant!r} does not belong to family {family!r}"
    )


def validate_request(request):
    """Fail closed on identity, family/variant, and planned chunk bounds."""
    if not isinstance(request, SourceRequest):
        raise RendererContractError("request must be a SourceRequest")
    if (
        isinstance(request.schema_version, bool)
        or not isinstance(request.schema_version, int)
        or request.schema_version != fixture_spec.SCHEMA_VERSION
    ):
        raise RendererContractError(
            f"unsupported fixture schema version: {request.schema_version!r}"
        )
    if type(request.persona_id) is not str:
        raise RendererContractError("persona id must be a string")
    if type(request.scope_key) is not str:
        raise RendererContractError("scope key must be a string")
    if type(request.family) is not str:
        raise RendererContractError("format family must be a string")
    if type(request.variant) is not str:
        raise RendererContractError("format variant must be a string")
    try:
        persona = fixture_spec.get_persona(request.persona_id)
    except KeyError as error:
        raise RendererContractError(f"unknown persona: {request.persona_id!r}") from error
    scope_keys = {scope["scope_key"] for scope in fixture_spec.scope_specs(persona)}
    if request.scope_key not in scope_keys:
        raise RendererContractError(
            f"scope {request.scope_key!r} does not belong to {request.persona_id!r}"
        )
    source_match = (
        _SOURCE_ID.fullmatch(request.source_id)
        if isinstance(request.source_id, str)
        else None
    )
    if source_match is None or source_match.group(1) != request.persona_id:
        raise RendererContractError(f"non-portable source id: {request.source_id!r}")
    if isinstance(request.version, bool) or not isinstance(request.version, int):
        raise RendererContractError("version must be an integer")
    if not 0 <= request.version <= 999_999:
        raise RendererContractError("version must be between 0 and 999999")
    gate_role, disposition = _variant_policy(request.family, request.variant)
    if request.variant not in _VARIANT_OUTPUT:
        raise RendererContractError(f"variant has no safe core renderer: {request.variant!r}")
    chunks = request.requested_contributor_chunks
    if isinstance(chunks, bool) or not isinstance(chunks, int):
        raise RendererContractError("requested contributor chunks must be an integer")
    if gate_role == "contract_contributor":
        if not 1 <= chunks <= fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE:
            raise RendererContractError(
                "contract contributor chunks must be between 1 and "
                f"{fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE}"
            )
    elif chunks != 0:
        raise RendererContractError(
            f"{gate_role}/{disposition} source must request zero contract chunks"
        )
    return gate_role, disposition


def _identity(request):
    return (
        f"schema-{request.schema_version} persona-{request.persona_id} "
        f"scope-{request.scope_key} source-{request.source_id} version-{request.version}"
        f" family-{request.family} variant-{request.variant}"
    )


def _identity_digest(request):
    return hashlib.sha256(_identity(request).encode("ascii")).hexdigest()


def _text_bytes(value):
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return (value.rstrip("\n") + "\n").encode("utf-8")


def _file_member(label, sections=(), chunks=0, kind="document", unit_key="doc:1"):
    return LogicalMember(unit_key, kind, 0, label, tuple(sections), chunks)


def _render_heading_text(request):
    headings = tuple(
        f"kio-{request.source_id}-v{request.version}-chunk-{index:03d}"
        for index in range(1, request.requested_contributor_chunks + 1)
    )
    digest = _identity_digest(request)
    sections = []
    for index, heading in enumerate(headings, start=1):
        section = (
            f"## {heading}\n\n"
            f"Deterministic persona evidence {digest[:20]} record {index}. "
            f"{_identity(request)}.\n\n"
        )
        if len(section) >= CHUNKING_MAX_CHARS:
            raise RendererContractError("heading section exceeds one-chunk bound")
        sections.append(section)
    return _text_bytes("".join(sections)), (_file_member(
        request.source_id, headings, request.requested_contributor_chunks
    ),)


def _render_code(request):
    chunks = request.requested_contributor_chunks
    normalized_chars = (chunks - 1) * CHUNKING_MAX_CHARS + CODE_LAST_CHUNK_CHARS
    fence_prefix = f"```{request.variant}\n"
    fence_suffix = "\n```\n"
    digest = _identity_digest(request)
    if request.variant == "py":
        comment_prefix = "# "
        suffix = f'\ndef kio_record():\n    return "{digest[:24]}"'
    elif request.variant == "rs":
        comment_prefix = "// "
        suffix = f'\npub fn kio_record() -> &\'static str {{ "{digest[:24]}" }}'
    elif request.variant == "ts":
        comment_prefix = "// "
        suffix = f'\nexport function kioRecord(): string {{ return "{digest[:24]}"; }}'
    else:  # protected by validate_request
        raise RendererContractError(f"unsupported code variant: {request.variant!r}")
    raw_chars = normalized_chars - len(fence_prefix) - len(fence_suffix)
    filler_chars = raw_chars - len(comment_prefix) - len(suffix)
    if filler_chars < 1:
        raise RendererContractError("code chunk plan is too small for valid source")
    source = comment_prefix + ("x" * filler_chars) + suffix
    normalized = fence_prefix + source + fence_suffix
    if len(normalized) != normalized_chars or "\n\n" in normalized:
        raise RendererContractError("code hard-split plan is not exact")
    section_keys = tuple(f"span:{index}" for index in range(1, chunks + 1))
    return _text_bytes(source), (_file_member(
        request.source_id, section_keys, chunks
    ),)


def _render_incidental_text(request):
    identity = _identity(request)
    digest = _identity_digest(request)
    variant = request.variant
    if variant == "log":
        value = (
            f"2026-07-13T00:00:00Z INFO source={request.source_id} version={request.version}\n"
            f"2026-07-13T00:00:01Z INFO digest={digest[:24]} scope={request.scope_key}\n"
        )
    elif variant == "jsonl":
        value = "\n".join(
            json.dumps(record, sort_keys=True, separators=(",", ":"))
            for record in (
                {"identity": identity, "ordinal": 1},
                {"digest": digest[:24], "ordinal": 2},
            )
        ) + "\n"
    elif variant == "json":
        value = json.dumps(
            {"digest": digest, "identity": identity, "schema": request.schema_version},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
    elif variant == "yaml":
        value = (
            f"schema: {request.schema_version}\n"
            f"persona: {request.persona_id}\n"
            f"scope: {request.scope_key}\n"
            f"source: {request.source_id}\n"
            f"version: {request.version}\n"
            f"digest: {digest}\n"
        )
    elif variant == "xml":
        value = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<record schema="{request.schema_version}" version="{request.version}">'
            f"<persona>{html.escape(request.persona_id)}</persona>"
            f"<scope>{html.escape(request.scope_key)}</scope>"
            f"<source>{html.escape(request.source_id)}</source>"
            f"<digest>{digest}</digest></record>\n"
        )
    elif variant == "sql":
        value = (
            "CREATE TABLE fixture_record (source_id TEXT NOT NULL, version INTEGER NOT NULL, digest TEXT NOT NULL);\n"
            f"INSERT INTO fixture_record VALUES ('{request.source_id}', {request.version}, '{digest}');\n"
        )
    elif variant in ("csv", "tsv"):
        buffer = io.StringIO(newline="")
        writer = csv.writer(
            buffer,
            delimiter="," if variant == "csv" else "\t",
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writerow(("persona", "scope", "source", "version", "digest"))
        writer.writerow((request.persona_id, request.scope_key, request.source_id, request.version, digest))
        value = buffer.getvalue()
    elif variant == "html":
        value = (
            "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(request.source_id)}</title></head><body>"
            f"<main data-version=\"{request.version}\"><p>{html.escape(identity)}</p>"
            f"<code>{digest}</code></main></body></html>\n"
        )
    elif variant == "eml":
        message = EmailMessage(policy=EMAIL_POLICY.clone(linesep="\n", max_line_length=78))
        message["From"] = "fixture-sender@example.invalid"
        message["To"] = "fixture-recipient@example.invalid"
        message["Date"] = "Mon, 13 Jul 2026 00:00:00 +0000"
        message["Message-ID"] = f"<{digest[:24]}@example.invalid>"
        message["Subject"] = f"Persona fixture {request.source_id}"
        message.set_content(identity + "\n" + digest)
        value = message.as_string()
    elif variant == "ipynb":
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": digest[:8],
                    "metadata": {},
                    "source": [identity + "\n"],
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "id": digest[8:16],
                    "metadata": {},
                    "outputs": [],
                    "source": [f'record = "{digest[:24]}"\n'],
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {"name": "python", "version": "3"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        value = json.dumps(notebook, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    else:
        raise RendererContractError(f"unsupported incidental variant: {variant!r}")
    return _text_bytes(value), (_file_member(request.source_id),)


def _pdf(objects):
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        if not body.endswith(b"\n"):
            output.extend(b"\n")
        output.extend(b"endobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _pdf_literal(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_text_pdf(request):
    pages = request.requested_contributor_chunks
    digest = _identity_digest(request)
    kids = []
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    members = []
    for index in range(1, pages + 1):
        page_id = 4 + (index - 1) * 2
        content_id = page_id + 1
        kids.append(f"{page_id} 0 R")
        text = _pdf_literal(
            f"KIO {request.source_id} version {request.version} page {index} evidence {digest[:20]}"
        )
        stream = f"BT /F1 10 Tf 72 720 Td ({text}) Tj ET\n".encode("ascii")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream")
        members.append(
            LogicalMember(f"page:{index}", "page", index - 1, f"Page {index}", ("span:1",), 1)
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages /Count {pages} /Kids [{' '.join(kids)}] >>"
    ).encode("ascii")
    return _pdf(objects), tuple(members)


def _render_scan_pdf(request):
    digest = bytes.fromhex(_identity_digest(request))
    pixels = bytes((digest[index] for index in range(12)))
    return _render_scan_pdf_pixels(pixels)


def _render_scan_pdf_pixels(pixels):
    if type(pixels) is not bytes or len(pixels) != 12:
        raise RendererContractError(
            "scan PDF pixels must be exactly four RGB pixels"
        )
    # ASCIIHex's stream alphabet is [0-9A-F>] and can never contain the PDF
    # text-object token ``BT``.  Compressed Flate bytes cannot make that
    # guarantee and produced real collisions at corpus cardinality.
    image_stream = pixels.hex().upper().encode("ascii") + b">"
    content = b"q 72 0 0 72 72 648 cm /Im0 Do Q\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
        (
            b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Filter /ASCIIHexDecode /Length "
            + str(len(image_stream)).encode("ascii")
            + b" >>\nstream\n"
            + image_stream
            + b"\nendstream"
        ),
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"endstream",
    ]
    data = _pdf(objects)
    if b"BT" in data:
        raise RendererContractError("scan PDF unexpectedly contains a text-layer BT token")
    return data, (
        LogicalMember("page:1", "page", 0, "Scanned page 1", (), 0),
        LogicalMember("image:0", "image", 1, "Page image", (), 0),
    )


def _xml(value):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + value).encode("utf-8")


def _core_properties(request):
    digest = _identity_digest(request)
    return _xml(
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{request.source_id}</dc:title><dc:identifier>{digest}</dc:identifier>"
        "</cp:coreProperties>"
    )


def _package_relationships(application_target, application_type):
    return _xml(
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{application_type}" Target="{application_target}"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _content_types(defaults, overrides):
    values = [
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    values.extend(
        f'<Default Extension="{extension}" ContentType="{content_type}"/>'
        for extension, content_type in defaults
    )
    values.extend(
        f'<Override PartName="/{part}" ContentType="{content_type}"/>'
        for part, content_type in overrides
    )
    values.append("</Types>")
    return _xml("".join(values))


def _app_properties(application):
    return _xml(
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        f"<Application>{application}</Application><AppVersion>1.0</AppVersion></Properties>"
    )


def _zip_package(parts):
    _validate_ooxml_parts(parts)
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(parts):
            info = ZipInfo(name, date_time=_FIXED_ZIP_EPOCH)
            info.compress_type = ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, parts[name])
    return output.getvalue()


def _relationship_source(rels_name):
    if rels_name == "_rels/.rels":
        return ""
    directory, leaf = posixpath.split(rels_name)
    if posixpath.basename(directory) != "_rels" or not leaf.endswith(".rels"):
        raise RendererContractError(f"invalid relationship part path: {rels_name}")
    parent = posixpath.dirname(directory)
    source_name = leaf[:-5]
    return posixpath.join(parent, source_name)


def _validate_ooxml_parts(parts):
    required = {"[Content_Types].xml", "_rels/.rels"}
    if not required.issubset(parts):
        raise RendererContractError("OOXML package lacks root content types or relationships")
    for name, value in parts.items():
        if name.endswith((".xml", ".rels")):
            try:
                ET.fromstring(value)
            except ET.ParseError as error:
                raise RendererContractError(f"invalid OOXML XML part: {name}") from error
    content_root = ET.fromstring(parts["[Content_Types].xml"])
    for override in content_root.findall("{*}Override"):
        target = override.attrib.get("PartName", "").lstrip("/")
        if target not in parts:
            raise RendererContractError(f"content type references missing part: {target}")
    for rels_name in sorted(name for name in parts if name.endswith(".rels")):
        source = _relationship_source(rels_name)
        base = posixpath.dirname(source)
        root = ET.fromstring(parts[rels_name])
        for relation in root.findall("{*}Relationship"):
            if relation.attrib.get("TargetMode") == "External":
                continue
            target = relation.attrib.get("Target", "")
            resolved = posixpath.normpath(posixpath.join(base, target)).lstrip("/")
            if resolved.startswith("../") or resolved not in parts:
                raise RendererContractError(
                    f"relationship {rels_name} references missing part: {target}"
                )


def _render_docx(request):
    identity = html.escape(_identity(request))
    parts = {
        "[Content_Types].xml": _content_types((), (
            ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
            ("docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
            ("docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
        )),
        "_rels/.rels": _package_relationships(
            "word/document.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
        ),
        "docProps/app.xml": _app_properties("KIO Persona Renderer"),
        "docProps/core.xml": _core_properties(request),
        "word/_rels/document.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
        ),
        "word/document.xml": _xml(
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t xml:space="preserve">{identity}</w:t></w:r></w:p>'
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
            "</w:body></w:document>"
        ),
    }
    return _zip_package(parts), (_file_member(request.source_id, kind="document"),)


def _render_xlsx(request):
    identity = html.escape(_identity(request))
    parts = {
        "[Content_Types].xml": _content_types((), (
            ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
            ("xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"),
            ("xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
            ("docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
            ("docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
        )),
        "_rels/.rels": _package_relationships(
            "xl/workbook.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
        ),
        "docProps/app.xml": _app_properties("KIO Persona Renderer"),
        "docProps/core.xml": _core_properties(request),
        "xl/_rels/workbook.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": _xml(
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>'
        ),
        "xl/workbook.xml": _xml(
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Fixture" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/worksheets/sheet1.xml": _xml(
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>{identity}</t></is></c></row>'
            f'<row r="2"><c r="A2" t="n"><v>{request.version}</v></c></row></sheetData></worksheet>'
        ),
    }
    return _zip_package(parts), (
        LogicalMember("sheet:fixture", "sheet", 0, "Fixture", (), 0),
    )


def _ppt_theme():
    return _xml(
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="KIO">'
        '<a:themeElements><a:clrScheme name="KIO"><a:dk1><a:srgbClr val="000000"/></a:dk1>'
        '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F497D"/></a:dk2>'
        '<a:lt2><a:srgbClr val="EEECE1"/></a:lt2><a:accent1><a:srgbClr val="4F81BD"/></a:accent1>'
        '<a:accent2><a:srgbClr val="C0504D"/></a:accent2><a:accent3><a:srgbClr val="9BBB59"/></a:accent3>'
        '<a:accent4><a:srgbClr val="8064A2"/></a:accent4><a:accent5><a:srgbClr val="4BACC6"/></a:accent5>'
        '<a:accent6><a:srgbClr val="F79646"/></a:accent6><a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>'
        '<a:fontScheme name="KIO"><a:majorFont><a:latin typeface="Arial"/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Arial"/></a:minorFont></a:fontScheme>'
        '<a:fmtScheme name="KIO"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
        '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
        '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
        '</a:fmtScheme></a:themeElements></a:theme>'
    )


def _ppt_sp_tree(text=""):
    shape = ""
    if text:
        shape = (
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Fixture Text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US"/>'
            f"<a:t>{html.escape(text)}</a:t></a:r><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp>"
        )
    return (
        '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
        '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' + shape + "</p:spTree>"
    )


def _render_pptx(request):
    identity = _identity(request)
    parts = {
        "[Content_Types].xml": _content_types((), (
            ("ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
            ("ppt/slides/slide1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"),
            ("ppt/slideLayouts/slideLayout1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
            ("ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
            ("ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
            ("docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
            ("docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
        )),
        "_rels/.rels": _package_relationships(
            "ppt/presentation.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
        ),
        "docProps/app.xml": _app_properties("KIO Persona Renderer"),
        "docProps/core.xml": _core_properties(request),
        "ppt/_rels/presentation.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>'
            "</Relationships>"
        ),
        "ppt/presentation.xml": _xml(
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
            '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
        ),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slideLayouts/slideLayout1.xml": _xml(
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">'
            f"<p:cSld name=\"Blank\">{_ppt_sp_tree()}</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
        ),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slideMasters/slideMaster1.xml": _xml(
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f"<p:cSld>{_ppt_sp_tree()}</p:cSld>"
            '<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>'
            '<p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>'
            '<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>'
        ),
        "ppt/slides/_rels/slide1.xml.rels": _xml(
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slides/slide1.xml": _xml(
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f"<p:cSld>{_ppt_sp_tree(identity)}</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
        ),
        "ppt/theme/theme1.xml": _ppt_theme(),
    }
    return _zip_package(parts), (
        LogicalMember("slide:1", "slide", 0, "Slide 1", (), 0),
    )


def _png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _encode_fixture_png_rgb(pixels):
    if type(pixels) is not bytes or len(pixels) != 12:
        raise RendererContractError(
            "fixture PNG pixels must be exactly four RGB pixels"
        )
    width = height = 2
    raw = b"".join(
        b"\x00" + pixels[row * 6:(row + 1) * 6]
        for row in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        )
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def decode_fixture_png_rgb(data):
    """Strictly decode the renderer's bounded 2x2 RGB PNG subset."""
    if type(data) is not bytes or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RendererContractError("parent is not a fixture PNG")
    if len(data) > 1024 * 1024:
        raise RendererContractError("fixture PNG exceeds the transform bound")
    cursor = 8
    chunks = []
    while cursor < len(data):
        if len(data) - cursor < 12:
            raise RendererContractError("fixture PNG has a truncated chunk")
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        cursor += 4
        if length > 1024 * 1024 or len(data) - cursor < length + 8:
            raise RendererContractError("fixture PNG chunk exceeds its bound")
        kind = data[cursor:cursor + 4]
        cursor += 4
        payload = data[cursor:cursor + length]
        cursor += length
        expected_crc = struct.unpack(">I", data[cursor:cursor + 4])[0]
        cursor += 4
        actual_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise RendererContractError("fixture PNG CRC mismatch")
        chunks.append((kind, payload))
        if kind == b"IEND":
            break
    if cursor != len(data) or [kind for kind, _payload in chunks] != [
        b"IHDR", b"IDAT", b"IEND"
    ]:
        raise RendererContractError("fixture PNG chunk layout is not canonical")
    ihdr = chunks[0][1]
    if ihdr != struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0):
        raise RendererContractError("fixture PNG IHDR is not canonical")
    inflater = zlib.decompressobj()
    raw = inflater.decompress(chunks[1][1], 15)
    if inflater.unconsumed_tail:
        raise RendererContractError("fixture PNG IDAT expands beyond its bound")
    raw += inflater.flush(16 - len(raw))
    if (
        len(raw) > 14
        or inflater.unused_data
        or inflater.unconsumed_tail
        or not inflater.eof
    ):
        raise RendererContractError("fixture PNG IDAT is not canonical zlib data")
    if len(raw) != 14 or raw[0] != 0 or raw[7] != 0:
        raise RendererContractError("fixture PNG scanlines are not canonical")
    return raw[1:7] + raw[8:14]


def _render_png(request):
    digest = bytes.fromhex(_identity_digest(request))
    data = _encode_fixture_png_rgb(digest[:12])
    return data, (LogicalMember("image:0", "image", 0, "Image", (), 0),)


def render_near_png(parent_data, child_request):
    """Create a valid near duplicate by changing exactly one RGB channel."""
    validate_request(child_request)
    if (
        child_request.family != "image"
        or child_request.variant != "png"
        or child_request.requested_contributor_chunks != 0
    ):
        raise RendererContractError("near PNG child request must be raw-only PNG")
    parent_pixels = decode_fixture_png_rgb(parent_data)
    selector = bytes.fromhex(_identity_digest(child_request))[0] % len(parent_pixels)
    before = parent_pixels[selector]
    after = before + 1 if before < 255 else before - 1
    child_pixels = bytearray(parent_pixels)
    child_pixels[selector] = after
    rendered = validate_rendered_source(
        child_request,
        RenderedSource(
            data=_encode_fixture_png_rgb(bytes(child_pixels)),
            extension="png",
            media_type="image/png",
            logical_members=(
                LogicalMember("image:0", "image", 0, "Near duplicate", (), 0),
            ),
            planned_contract_chunks=0,
        ),
    )
    witness = {
        "kind": "near-png-one-channel/v1",
        "parent_raw_sha256": hashlib.sha256(parent_data).hexdigest(),
        "child_raw_sha256": hashlib.sha256(rendered.data).hexdigest(),
        "changed_channel_index": selector,
        "before_channel_value": before,
        "after_channel_value": after,
        "parent_pixel_sha256": hashlib.sha256(parent_pixels).hexdigest(),
        "child_pixel_sha256": hashlib.sha256(bytes(child_pixels)).hexdigest(),
    }
    return rendered, witness


def render_scan_pdf_from_png(parent_data, child_request):
    """Embed the parent's decoded RGB pixels in a text-layer-free scan PDF."""
    validate_request(child_request)
    if (
        child_request.family != "pdf_scan"
        or child_request.variant != "pdf-scan"
        or child_request.requested_contributor_chunks != 0
    ):
        raise RendererContractError(
            "derived scan PDF child request must be raw-only pdf-scan"
        )
    parent_pixels = decode_fixture_png_rgb(parent_data)
    data, members = _render_scan_pdf_pixels(parent_pixels)
    rendered = validate_rendered_source(
        child_request,
        RenderedSource(
            data=data,
            extension="pdf",
            media_type="application/pdf",
            logical_members=members,
            planned_contract_chunks=0,
        ),
    )
    witness = {
        "kind": "png-to-scan-pdf/v1",
        "parent_raw_sha256": hashlib.sha256(parent_data).hexdigest(),
        "child_raw_sha256": hashlib.sha256(rendered.data).hexdigest(),
        "embedded_pixel_sha256": hashlib.sha256(parent_pixels).hexdigest(),
        "embedded_pixel_bytes": len(parent_pixels),
        "contains_text_layer_bt": False,
    }
    return rendered, witness


def _render_wav(request):
    digest = bytes.fromhex(_identity_digest(request))
    samples = []
    for index in range(160):
        value = ((digest[index % len(digest)] - 128) * 128)
        samples.append(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        wav_file.writeframes(b"".join(samples))
    return output.getvalue(), (
        LogicalMember("audio:1", "audio", 0, "Audio clip", (), 0),
    )


def _internet_checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _render_pcap(request):
    digest = bytes.fromhex(_identity_digest(request))
    payload = b"KIO1" + digest[:20]
    source_ip = b"\xc0\x00\x02\x01"
    destination_ip = b"\xc6\x33\x64\x02"
    udp_length = 8 + len(payload)
    source_port = 40_000 + digest[0]
    destination_port = 9_000 + digest[1]
    udp_without_checksum = struct.pack("!HHHH", source_port, destination_port, udp_length, 0)
    pseudo_header = source_ip + destination_ip + b"\x00\x11" + struct.pack("!H", udp_length)
    udp_checksum = _internet_checksum(pseudo_header + udp_without_checksum + payload) or 0xFFFF
    udp = struct.pack("!HHHH", source_port, destination_port, udp_length, udp_checksum) + payload
    total_length = 20 + len(udp)
    ip_without_checksum = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, total_length, int.from_bytes(digest[2:4], "big"), 0x4000,
        64, 17, 0, source_ip, destination_ip,
    )
    ip = ip_without_checksum[:10] + struct.pack("!H", _internet_checksum(ip_without_checksum)) + ip_without_checksum[12:]
    ethernet = b"\x02\x00\x00\x00\x00\x02\x02\x00\x00\x00\x00\x01\x08\x00"
    packet = ethernet + ip + udp
    global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    packet_header = struct.pack(
        "<IIII", 1_700_000_000 + request.version, int.from_bytes(digest[4:7], "big") % 1_000_000,
        len(packet), len(packet),
    )
    return global_header + packet_header + packet, (
        LogicalMember("packet:1", "packet", 0, "Ethernet IPv4 UDP packet", (), 0),
    )


def validate_rendered_source(request, rendered):
    """Validate renderer-level safety and metadata before a file is published."""
    validate_request(request)
    if not isinstance(rendered, RenderedSource):
        raise RendererContractError("renderer result must be a RenderedSource")
    if rendered.renderer_id != RENDERER_ID or rendered.renderer_schema_version != RENDERER_SCHEMA_VERSION:
        raise RendererContractError("renderer identity/schema mismatch")
    extension, media_type = _VARIANT_OUTPUT[request.variant]
    if (rendered.extension, rendered.media_type) != (extension, media_type):
        raise RendererContractError("extension/media type mismatch")
    if (
        type(rendered.data) is not bytes
        or not rendered.data
        or len(rendered.data) > MAX_RENDERED_SOURCE_BYTES
    ):
        raise RendererContractError("rendered source violates byte bounds")
    if rendered.planned_contract_chunks != request.requested_contributor_chunks:
        raise RendererContractError("planned contract chunk count mismatch")
    if type(rendered.logical_members) is not tuple or not rendered.logical_members:
        raise RendererContractError("rendered source has no logical members")
    unit_keys = set()
    for expected_ordinal, member in enumerate(rendered.logical_members):
        if type(member) is not LogicalMember:
            raise RendererContractError("logical member must be a LogicalMember")
        if (
            type(member.unit_key) is not str
            or _SAFE_MEMBER_KEY.fullmatch(member.unit_key) is None
            or member.unit_key in unit_keys
        ):
            raise RendererContractError("logical member unit key must be safe and unique")
        unit_keys.add(member.unit_key)
        if type(member.kind) is not str or member.kind not in _LOGICAL_MEMBER_KINDS:
            raise RendererContractError("logical member kind is not allowed")
        if (
            type(member.ordinal) is not int
            or member.ordinal != expected_ordinal
        ):
            raise RendererContractError(
                "logical member ordinals must be contiguous, unique, and ordered"
            )
        if (
            type(member.label) is not str
            or not member.label
            or any(
                unicodedata.category(character).startswith("C")
                for character in member.label
            )
            or unicodedata.normalize("NFC", member.label) != member.label
            or len(member.label.encode("utf-8")) > 256
        ):
            raise RendererContractError("logical member label must be bounded NFC text")
        section_keys = member.planned_section_keys
        if type(section_keys) is not tuple:
            raise RendererContractError("planned section keys must be a tuple")
        if any(
            type(section_key) is not str
            or _SAFE_MEMBER_KEY.fullmatch(section_key) is None
            for section_key in section_keys
        ):
            raise RendererContractError("planned section keys must be safe strings")
        if len(set(section_keys)) != len(section_keys):
            raise RendererContractError("planned section keys must be unique")
        if (
            type(member.planned_contract_chunks) is not int
            or not 0 <= member.planned_contract_chunks <= fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
        ):
            raise RendererContractError(
                "logical member planned chunks must be a bounded non-negative integer"
            )
    if sum(member.planned_contract_chunks for member in rendered.logical_members) != rendered.planned_contract_chunks:
        raise RendererContractError("logical member contract chunks do not sum to source plan")
    if request.variant in ("docx", "xlsx", "pptx"):
        with ZipFile(io.BytesIO(rendered.data)) as archive:
            names = archive.namelist()
            if names != sorted(names) or any(info.compress_type != ZIP_STORED for info in archive.infolist()):
                raise RendererContractError("OOXML ZIP order/compression is not deterministic")
            if any(info.date_time != _FIXED_ZIP_EPOCH for info in archive.infolist()):
                raise RendererContractError("OOXML ZIP timestamp is not fixed")
            _validate_ooxml_parts({name: archive.read(name) for name in names})
    if request.variant == "pdf-scan" and b"BT" in rendered.data:
        raise RendererContractError("scan PDF contains a text-layer BT token")
    return rendered


def render_source(request):
    """Render one bounded source to deterministic bytes and planned metadata."""
    gate_role, _disposition = validate_request(request)
    variant = request.variant
    if variant in ("md", "markdown", "txt"):
        data, members = _render_heading_text(request)
    elif variant in ("py", "rs", "ts"):
        data, members = _render_code(request)
    elif variant in ("log", "jsonl", "json", "yaml", "xml", "sql", "csv", "tsv", "html", "eml", "ipynb"):
        data, members = _render_incidental_text(request)
    elif variant == "pdf-text":
        data, members = _render_text_pdf(request)
    elif variant == "pdf-scan":
        data, members = _render_scan_pdf(request)
    elif variant == "docx":
        data, members = _render_docx(request)
    elif variant == "xlsx":
        data, members = _render_xlsx(request)
    elif variant == "pptx":
        data, members = _render_pptx(request)
    elif variant == "png":
        data, members = _render_png(request)
    elif variant == "wav":
        data, members = _render_wav(request)
    elif variant == "pcap":
        data, members = _render_pcap(request)
    else:  # validate_request fails first; defensive for future table changes
        raise RendererContractError(f"no safe renderer for variant: {variant!r}")
    extension, media_type = _VARIANT_OUTPUT[variant]
    planned = request.requested_contributor_chunks if gate_role == "contract_contributor" else 0
    return validate_rendered_source(request, RenderedSource(
        data=data,
        extension=extension,
        media_type=media_type,
        logical_members=members,
        planned_contract_chunks=planned,
    ))
