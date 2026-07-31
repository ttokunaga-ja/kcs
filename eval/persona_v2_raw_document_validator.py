"""Standalone bounded validator for four persona-PC v2 raw documents.

The validator duplicates all metadata, formulas, PDF objects, OOXML parts,
and classic ZIP_STORED framing that it accepts.  It deliberately imports no
renderer, catalog, or planning module.  A successful receipt attests only
bounded local bytes and structure, never source identity, physical placement,
KIO execution, observed chunks, history, solver output, or G0 completion.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import io
import posixpath
import re
import struct
import xml.etree.ElementTree as ET
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-raw-document-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-document-validator"
VALIDATOR_ID = "persona-v2-id-free-raw-document-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 96 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_PDF_NON_STREAM_LINE_BYTES = 255
MAX_ZIP_MEMBERS = 128
MAX_XML_PART_BYTES = 512 * 1024
MAX_XML_ELEMENTS = 4_096
MAX_XML_DEPTH = 32
FIXED_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
ZIP_CREATOR_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_DOS_TIME = 0
ZIP_DOS_DATE = 33
ZIP_EXTERNAL_ATTRIBUTES = 0x20

READY_VARIANTS = ("docx", "pdf-scan", "pptx", "xlsx")

REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "target_complexity",
    "data",
    "extension",
    "content_media_type",
    "expected_kio_path_media_type",
    "expected_offline_disposition",
)

PROHIBITED_IDENTITY_FIELDS = (
    "digest",
    "final_id",
    "final_source_id",
    "intent_id",
    "materialization_id",
    "payload_seed",
    "persona_id",
    "query_id",
    "query_key",
    "scope_id",
    "scope_key",
    "source_id",
)

_VARIANT_ROWS = {
    "docx": {
        "base_bytes": 8_192,
        "complexity_measure": "document-sections",
        "content_media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "expected_kio_path_media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "expected_offline_disposition": "await_conversion",
        "family": "docx",
        "filename_extension": "docx",
        "inclusive_maximum": 64,
        "inclusive_minimum": 1,
        "increment_bytes": 2_048,
        "render_template": "canonical-stored-wordprocessingml-sections-v2",
    },
    "pdf-scan": {
        "base_bytes": 8_192,
        "complexity_measure": "scan-pages",
        "content_media_type": "application/pdf",
        "expected_kio_path_media_type": "application/pdf",
        "expected_offline_disposition": "awaiting_ocr",
        "family": "pdf_scan",
        "filename_extension": "pdf",
        "inclusive_maximum": 50,
        "inclusive_minimum": 1,
        "increment_bytes": 4_096,
        "render_template": "canonical-image-xobject-scan-pdf-v2",
    },
    "pptx": {
        "base_bytes": 16_384,
        "complexity_measure": "slides",
        "content_media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "expected_kio_path_media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "expected_offline_disposition": "await_conversion",
        "family": "pptx",
        "filename_extension": "pptx",
        "inclusive_maximum": 40,
        "inclusive_minimum": 1,
        "increment_bytes": 8_192,
        "render_template": "canonical-stored-presentationml-slides-v2",
    },
    "xlsx": {
        "base_bytes": 12_288,
        "complexity_measure": "worksheets",
        "content_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "expected_kio_path_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "expected_offline_disposition": "await_conversion",
        "family": "xlsx",
        "filename_extension": "xlsx",
        "inclusive_maximum": 20,
        "inclusive_minimum": 1,
        "increment_bytes": 6_144,
        "render_template": "canonical-stored-spreadsheetml-worksheets-v2",
    },
}

_COMPLEXITY_COUNTING_RULES = {
    "docx": "wordprocessingml-section-properties-elements",
    "pdf-scan": "page-tree-leaf-pages-each-with-one-image-xobject",
    "pptx": "presentation-slide-identifiers-and-internal-slide-parts",
    "xlsx": "workbook-sheet-elements-and-internal-worksheet-parts",
}

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
_XML_DECLARATION_BYTES = _XML_DECLARATION.encode("ascii")
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
)
_PDF_HEADER = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
_PDF_PADDING_BYTE = b"x"

_LOCAL_FILE_HEADER = struct.Struct("<IHHHHHIIIHH")
_CENTRAL_DIRECTORY_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
_END_OF_CENTRAL_DIRECTORY = struct.Struct("<IHHHHIIH")
_LOCAL_FILE_SIGNATURE = 0x04034B50
_CENTRAL_DIRECTORY_SIGNATURE = 0x02014B50
_END_OF_CENTRAL_DIRECTORY_SIGNATURE = 0x06054B50

_STARTXREF_RE = re.compile(rb"startxref\n([0-9]{1,10})\n%%EOF\n\Z")
_XREF_ENTRY_RE = re.compile(rb"[0-9]{10} 00000 n ")
_FORBIDDEN_IDENTITY_PATTERN = re.compile(
    rb"(?:"
    rb"\bp[0-9]{2}-src-[0-9]{6}\b|"
    rb"\b(?:persona|scope|source|intent|materialization|query|final[_-]?source)"
    rb"[_-]?(?:id|key)\s*[:=]|"
    rb"\b(?:sha256|digest)\s*[:=]|"
    rb"\b[0-9a-f]{64}\b"
    rb")",
    re.IGNORECASE,
)
_FORBIDDEN_PDF_TOKENS = (
    b"/AA",
    b"/AcroForm",
    b"/EmbeddedFile",
    b"/Encrypt",
    b"/Filespec",
    b"/Font",
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/OpenAction",
    b"/RichMedia",
    b"/ToUnicode",
    b"/URI",
    b"/XFA",
)
_FORBIDDEN_OOXML_TOKENS = (
    b"activex",
    b"attachedtemplate",
    b"dde",
    b"externallink",
    b"macrosenabled",
    b"oleobject",
    b"vbaproject",
    b"xl4macro",
)


class PersonaV2RawDocumentValidatorError(ValueError):
    """Raised when raw-document bytes or metadata violate the contract."""


@dataclass(frozen=True, slots=True)
class RawDocumentValidationRequest:
    """The complete identity-free raw-document payload for validation."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str


def _fail(message):
    raise PersonaV2RawDocumentValidatorError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unsupported raw document variant")
    return _VARIANT_ROWS[variant]


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= target_complexity
        <= profile["inclusive_maximum"]
    ):
        _fail("target complexity is outside the exact variant domain")
    target = profile["base_bytes"] + (
        target_complexity - profile["inclusive_minimum"]
    ) * profile["increment_bytes"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("target-byte formula exceeds the standalone validator cap")
    return target


def _validate_request_shape(request):
    if type(request) is not RawDocumentValidationRequest:
        _fail("request must be an exact RawDocumentValidationRequest")
    if tuple(RawDocumentValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        _fail("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        _fail("validator request exposes an identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("validator request schema version must be exact 2")
    profile = _profile(request.variant)
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if type(request.data) is not bytes:
        _fail("validated payload must be exact bytes")
    if not request.data or len(request.data) > MAX_RENDERED_BYTES:
        _fail("validated payload exceeds byte bounds")
    if len(request.data) != target_bytes:
        _fail("payload violates exact affine target-byte formula")
    metadata = (
        request.extension,
        request.content_media_type,
        request.expected_kio_path_media_type,
        request.expected_offline_disposition,
    )
    if any(type(value) is not str for value in metadata):
        _fail("format metadata must be exact strings")
    expected = (
        profile["filename_extension"],
        profile["content_media_type"],
        profile["expected_kio_path_media_type"],
        profile["expected_offline_disposition"],
    )
    if metadata != expected:
        _fail("extension/MIME/disposition metadata drifted")
    if _FORBIDDEN_IDENTITY_PATTERN.search(request.data):
        _fail("payload contains a prohibited identity-shaped token")
    return profile, target_bytes


def _scan_pixels(page_number):
    return bytes((page_number * 17 + offset) % 251 for offset in range(256))


def _expected_pdf_objects(page_count):
    kids = []
    objects = [b"", b""]
    for page_number in range(1, page_count + 1):
        page_object = 3 + (page_number - 1) * 3
        image_object = page_object + 1
        content_object = page_object + 2
        kids.append(f"{page_object} 0 R")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /XObject << /Im0 {image_object} 0 R >> >> "
                f"/Contents {content_object} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width 16 /Height 16 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 256 >>\n"
            b"stream\n"
            + _scan_pixels(page_number)
            + b"\nendstream"
        )
        stream = b"q\n576 0 0 756 18 18 cm\n/Im0 Do\nQ\n"
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"endstream"
        )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        f"<< /Type /Pages\n/Count {page_count}\n/Kids [\n"
        + "\n".join(kids)
        + "\n] >>"
    ).encode("ascii")
    return objects


def _expected_pdf_padding(length):
    if type(length) is not int or length < 2:
        _fail("PDF padding comment must be at least two bytes")
    full_records, remainder = divmod(length, MAX_PDF_NON_STREAM_LINE_BYTES + 1)
    record_lengths = [MAX_PDF_NON_STREAM_LINE_BYTES + 1] * full_records
    if remainder == 1:
        if not record_lengths:
            _fail("PDF padding cannot encode a one-byte comment")
        record_lengths[-1] -= 1
        record_lengths.append(2)
    elif remainder:
        record_lengths.append(remainder)
    return b"".join(
        b"%" + _PDF_PADDING_BYTE * (record_length - 2) + b"\n"
        for record_length in record_lengths
    )


def _assemble_expected_pdf(objects, padding_length):
    output = bytearray(_PDF_HEADER)
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(body)
        if not body.endswith(b"\n"):
            output.extend(b"\n")
        output.extend(b"endobj\n")
    if padding_length:
        output.extend(_expected_pdf_padding(padding_length))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        if offset > 9_999_999_999:
            _fail("PDF object offset exceeds xref width")
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _expected_pdf(page_count, target_bytes):
    objects = _expected_pdf_objects(page_count)
    padding_length = target_bytes - len(_assemble_expected_pdf(objects, 0))
    if padding_length < 2:
        _fail("affine target leaves no valid PDF padding comment")
    for _ in range(8):
        data = _assemble_expected_pdf(objects, padding_length)
        delta = target_bytes - len(data)
        if delta == 0:
            return data
        padding_length += delta
        if padding_length < 2:
            break
    _fail("could not reconstruct exact affine PDF bytes")


def _validate_pdf_structure(data, page_count):
    if not data.startswith(_PDF_HEADER):
        _fail("PDF header or binary marker drifted")
    if data.count(b"%%EOF") != 1:
        _fail("PDF must contain exactly one EOF marker")
    if any(token in data for token in _FORBIDDEN_PDF_TOKENS):
        _fail("PDF contains a forbidden active or text-layer feature")
    if b"BT" in data or b"ET" in data:
        _fail("scan PDF contains a text-object operator")
    match = _STARTXREF_RE.search(data)
    if match is None:
        _fail("PDF must end with one exact startxref/EOF trailer")
    xref_offset = int(match.group(1))
    if xref_offset < len(_PDF_HEADER) or not data.startswith(b"xref\n", xref_offset):
        _fail("startxref does not point to the xref table")

    object_count = 2 + 3 * page_count
    xref_count = object_count + 1
    lines = data[xref_offset:].splitlines()
    trailer_index = 2 + xref_count
    if len(lines) != xref_count + 7:
        _fail("xref/trailer line count drifted")
    if lines[0] != b"xref" or lines[1] != f"0 {xref_count}".encode("ascii"):
        _fail("xref subsection shape drifted")
    if lines[2] != b"0000000000 65535 f ":
        _fail("xref free entry drifted")

    offsets = []
    for object_number in range(1, object_count + 1):
        line = lines[2 + object_number]
        if not _XREF_ENTRY_RE.fullmatch(line):
            _fail("xref in-use entry drifted")
        offset = int(line[:10])
        if offset >= xref_offset or (offsets and offset <= offsets[-1]):
            _fail("xref object offsets are not strictly bounded")
        if not data.startswith(f"{object_number} 0 obj\n".encode("ascii"), offset):
            _fail("xref entry does not point to its numbered object")
        offsets.append(offset)
    exact_trailer = (
        b"trailer",
        f"<< /Size {xref_count} /Root 1 0 R >>".encode("ascii"),
        b"startxref",
        str(xref_offset).encode("ascii"),
        b"%%EOF",
    )
    if tuple(lines[trailer_index:]) != exact_trailer:
        _fail("PDF trailer dictionary drifted")

    bodies = []
    padding = b""
    for index, offset in enumerate(offsets):
        object_number = index + 1
        marker = f"{object_number} 0 obj\n".encode("ascii")
        body_start = offset + len(marker)
        boundary = offsets[index + 1] if index + 1 < len(offsets) else xref_offset
        segment = data[body_start:boundary]
        end_marker = b"\nendobj\n"
        if index + 1 < len(offsets):
            if not segment.endswith(end_marker):
                _fail("bytes occur between consecutive PDF objects")
            bodies.append(segment[: -len(end_marker)])
        else:
            end_at = segment.find(end_marker)
            if end_at < 0:
                _fail("final PDF object has no exact endobj")
            bodies.append(segment[:end_at])
            padding = segment[end_at + len(end_marker) :]
    if not padding or not padding.endswith(b"\n"):
        _fail("PDF has no exact pre-xref comment padding")
    for line in padding.splitlines():
        if (
            not line.startswith(b"%")
            or set(line[1:]) - {ord("x")}
            or len(line) > MAX_PDF_NON_STREAM_LINE_BYTES
        ):
            _fail("PDF padding comment framing drifted")

    expected_bodies = _expected_pdf_objects(page_count)
    if bodies != expected_bodies:
        _fail("PDF page/image/content object structure drifted")
    if sum(body.count(b"/Subtype /Image") for body in bodies) != page_count:
        _fail("scan PDF image XObject count drifted")
    if sum(body.count(b"/Type /Page ") for body in bodies) != page_count:
        _fail("scan PDF page count drifted")


def _safe_member_name(name):
    if (
        type(name) is not str
        or not name
        or not name.isascii()
        or name.startswith("/")
        or name.endswith("/")
        or "\\" in name
        or ":" in name
        or "%" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        _fail("unsafe OOXML member path")


def _parse_bounded_stored_zip(data):
    if len(data) < _END_OF_CENTRAL_DIRECTORY.size:
        _fail("OOXML ZIP is shorter than its EOCD")
    eocd_offset = len(data) - _END_OF_CENTRAL_DIRECTORY.size
    values = _END_OF_CENTRAL_DIRECTORY.unpack_from(data, eocd_offset)
    (
        signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_length,
    ) = values
    if signature != _END_OF_CENTRAL_DIRECTORY_SIGNATURE:
        _fail("OOXML ZIP lacks one exact EOCD at EOF")
    if (
        disk_number != 0
        or central_disk != 0
        or disk_entries != total_entries
        or not 1 <= total_entries <= MAX_ZIP_MEMBERS
        or comment_length != 0
        or central_offset + central_size != eocd_offset
    ):
        _fail("OOXML EOCD fields are non-canonical or out of bounds")

    position = central_offset
    central_rows = []
    for _ in range(total_entries):
        if position + _CENTRAL_DIRECTORY_HEADER.size > eocd_offset:
            _fail("OOXML central directory header is truncated")
        values = _CENTRAL_DIRECTORY_HEADER.unpack_from(data, position)
        (
            signature,
            creator_version,
            extract_version,
            flags,
            method,
            dos_time,
            dos_date,
            crc32,
            compressed_size,
            uncompressed_size,
            name_length,
            extra_length,
            member_comment_length,
            member_disk,
            internal_attributes,
            external_attributes,
            local_offset,
        ) = values
        position += _CENTRAL_DIRECTORY_HEADER.size
        variable_length = name_length + extra_length + member_comment_length
        if position + variable_length > eocd_offset:
            _fail("OOXML central directory variable fields are truncated")
        name_bytes = data[position : position + name_length]
        position += variable_length
        try:
            name = name_bytes.decode("ascii")
        except UnicodeDecodeError:
            _fail("OOXML member name is not exact ASCII")
        _safe_member_name(name)
        if (
            creator_version != ZIP_CREATOR_VERSION
            or extract_version != ZIP_EXTRACT_VERSION
            or flags != 0
            or method != 0
            or dos_time != ZIP_DOS_TIME
            or dos_date != ZIP_DOS_DATE
            or compressed_size != uncompressed_size
            or uncompressed_size > MAX_XML_PART_BYTES
            or not name_length
            or extra_length != 0
            or member_comment_length != 0
            or member_disk != 0
            or internal_attributes != 0
            or external_attributes != ZIP_EXTERNAL_ATTRIBUTES
        ):
            _fail("OOXML central directory metadata is non-canonical")
        central_rows.append(
            (name, name_bytes, crc32, uncompressed_size, local_offset)
        )
    if position != eocd_offset:
        _fail("OOXML central directory size/count drifted")
    names = [row[0] for row in central_rows]
    if names != sorted(names) or len(names) != len(set(names)):
        _fail("OOXML members must be unique and lexical")
    if len({name.casefold() for name in names}) != len(names):
        _fail("OOXML member paths collide case-insensitively")

    parts = {}
    expected_local_offset = 0
    for name, name_bytes, central_crc, payload_size, local_offset in central_rows:
        if local_offset != expected_local_offset:
            _fail("OOXML local members overlap, have gaps, or have a preamble")
        if local_offset + _LOCAL_FILE_HEADER.size > central_offset:
            _fail("OOXML local header is truncated")
        values = _LOCAL_FILE_HEADER.unpack_from(data, local_offset)
        (
            signature,
            extract_version,
            flags,
            method,
            dos_time,
            dos_date,
            crc32,
            compressed_size,
            uncompressed_size,
            name_length,
            extra_length,
        ) = values
        name_start = local_offset + _LOCAL_FILE_HEADER.size
        payload_start = name_start + name_length + extra_length
        payload_end = payload_start + compressed_size
        if payload_end > central_offset:
            _fail("OOXML local payload exceeds its bounded data area")
        if (
            signature != _LOCAL_FILE_SIGNATURE
            or extract_version != ZIP_EXTRACT_VERSION
            or flags != 0
            or method != 0
            or dos_time != ZIP_DOS_TIME
            or dos_date != ZIP_DOS_DATE
            or crc32 != central_crc
            or compressed_size != payload_size
            or uncompressed_size != payload_size
            or name_length != len(name_bytes)
            or extra_length != 0
            or data[name_start : name_start + name_length] != name_bytes
        ):
            _fail("OOXML local/central header cross-check failed")
        payload = data[payload_start:payload_end]
        if zlib.crc32(payload) & 0xFFFFFFFF != central_crc:
            _fail("OOXML member CRC does not match its bytes")
        parts[name] = payload
        expected_local_offset = payload_end
    if expected_local_offset != central_offset:
        _fail("OOXML local file area does not end at the central directory")
    return parts


def _xml(body):
    if type(body) is not str or not body.isascii():
        _fail("expected OOXML body must be exact ASCII")
    return (_XML_DECLARATION + body + "\n").encode("ascii")


def _relationship_part(relations):
    return _xml(
        f'<Relationships xmlns="{_REL_NS}">'
        + "".join(
            f'<Relationship Id="{relation_id}" Type="{relation_type}" Target="{target}"/>'
            for relation_id, relation_type, target in relations
        )
        + "</Relationships>"
    )


def _root_relationships(application_target, application_relation):
    return _relationship_part(
        (
            ("rId1", _OFFICE_REL + application_relation, application_target),
            (
                "rId2",
                "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
                "docProps/core.xml",
            ),
            (
                "rId3",
                _OFFICE_REL + "extended-properties",
                "docProps/app.xml",
            ),
        )
    )


def _core_properties(padding_length):
    if type(padding_length) is not int or padding_length < 0:
        _fail("expected OOXML padding must be a non-negative integer")
    return _xml(
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>Bounded local document feasibility</dc:title>'
        f'<dc:description>{"x" * padding_length}</dc:description>'
        "</cp:coreProperties>"
    )


def _app_properties(application, _complexity_name, _complexity):
    return _xml(
        '<Properties '
        'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        f"<Application>{application}</Application>"
        "<AppVersion>1.0</AppVersion></Properties>"
    )


def _content_types(overrides):
    return _xml(
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(
            f'<Override PartName="/{name}" ContentType="{content_type}"/>'
            for name, content_type in overrides
        )
        + "</Types>"
    )


def _common_parts(application_target, application_relation, application, label, complexity):
    return {
        "_rels/.rels": _root_relationships(application_target, application_relation),
        "docProps/app.xml": _app_properties(application, label, complexity),
        "docProps/core.xml": _core_properties(0),
    }


def _expected_docx_parts(section_count):
    parts = _common_parts(
        "word/document.xml",
        "officeDocument",
        "Bounded WordprocessingML",
        "Pages",
        section_count,
    )
    section_paragraphs = []
    for ordinal in range(1, section_count):
        section_paragraphs.append(
            '<w:p><w:pPr><w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
            f'</w:sectPr></w:pPr><w:r><w:t>Bounded section {ordinal:03d}'
            "</w:t></w:r></w:p>"
        )
    section_paragraphs.append(
        f'<w:p><w:r><w:t>Bounded section {section_count:03d}</w:t></w:r></w:p>'
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr>"
    )
    parts.update(
        {
            "word/_rels/document.xml.rels": _relationship_part(()),
            "word/document.xml": _xml(
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                + "".join(section_paragraphs)
                + "</w:body></w:document>"
            ),
        }
    )
    parts["[Content_Types].xml"] = _content_types(
        (
            (
                "word/document.xml",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            ),
            (
                "docProps/core.xml",
                "application/vnd.openxmlformats-package.core-properties+xml",
            ),
            (
                "docProps/app.xml",
                "application/vnd.openxmlformats-officedocument.extended-properties+xml",
            ),
        )
    )
    return parts


def _expected_xlsx_styles():
    return _xml(
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>'
    )


def _expected_xlsx_parts(worksheet_count):
    parts = _common_parts(
        "xl/workbook.xml",
        "officeDocument",
        "Bounded SpreadsheetML",
        "Worksheets",
        worksheet_count,
    )
    sheets = []
    relations = []
    overrides = [
        (
            "xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        ),
        (
            "xl/styles.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
        ),
    ]
    for ordinal in range(1, worksheet_count + 1):
        leaf = f"sheet{ordinal:03d}.xml"
        sheets.append(
            f'<sheet name="Sheet{ordinal:03d}" sheetId="{ordinal}" r:id="rId{ordinal}"/>'
        )
        relations.append(
            (f"rId{ordinal}", _OFFICE_REL + "worksheet", f"worksheets/{leaf}")
        )
        part_name = f"xl/worksheets/{leaf}"
        parts[part_name] = _xml(
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Bounded worksheet {ordinal:03d}'
            "</t></is></c></row></sheetData></worksheet>"
        )
        overrides.append(
            (
                part_name,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            )
        )
    relations.append(
        (
            f"rId{worksheet_count + 1}",
            _OFFICE_REL + "styles",
            "styles.xml",
        )
    )
    parts.update(
        {
            "xl/_rels/workbook.xml.rels": _relationship_part(relations),
            "xl/styles.xml": _expected_xlsx_styles(),
            "xl/workbook.xml": _xml(
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<sheets>"
                + "".join(sheets)
                + "</sheets></workbook>"
            ),
        }
    )
    overrides.extend(
        (
            (
                "docProps/core.xml",
                "application/vnd.openxmlformats-package.core-properties+xml",
            ),
            (
                "docProps/app.xml",
                "application/vnd.openxmlformats-officedocument.extended-properties+xml",
            ),
        )
    )
    parts["[Content_Types].xml"] = _content_types(overrides)
    return parts


def _ppt_sp_tree(text=""):
    shape = ""
    if text:
        shape = (
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Bounded Text"/>'
            '<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr/>'
            '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r>'
            f'<a:rPr lang="en-US"/><a:t>{text}</a:t></a:r>'
            '<a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
        )
    return (
        '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        '<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
        '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
        '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + shape
        + "</p:spTree>"
    )


def _expected_ppt_theme():
    return _xml(
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Bounded">'
        '<a:themeElements><a:clrScheme name="Bounded">'
        '<a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
        '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
        '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
        '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6>'
        '<a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
        '</a:clrScheme><a:fontScheme name="Bounded"><a:majorFont><a:latin typeface="Arial"/>'
        '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Arial"/>'
        '<a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
        '<a:fmtScheme name="Bounded"><a:fillStyleLst>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:fillStyleLst>'
        '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
        '<a:ln w="25400"><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:ln>'
        '<a:ln w="38100"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:ln></a:lnStyleLst>'
        '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:bgFillStyleLst>'
        "</a:fmtScheme></a:themeElements></a:theme>"
    )


def _expected_pptx_parts(slide_count):
    parts = _common_parts(
        "ppt/presentation.xml",
        "officeDocument",
        "Bounded PresentationML",
        "Slides",
        slide_count,
    )
    slide_ids = []
    presentation_relations = [
        ("rId1", _OFFICE_REL + "slideMaster", "slideMasters/slideMaster1.xml")
    ]
    overrides = [
        (
            "ppt/presentation.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        ),
        (
            "ppt/presProps.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml",
        ),
        (
            "ppt/slideLayouts/slideLayout1.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
        ),
        (
            "ppt/slideMasters/slideMaster1.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
        ),
        (
            "ppt/theme/theme1.xml",
            "application/vnd.openxmlformats-officedocument.theme+xml",
        ),
    ]
    for ordinal in range(1, slide_count + 1):
        relation_id = f"rId{ordinal + 1}"
        leaf = f"slide{ordinal:03d}.xml"
        slide_ids.append(
            f'<p:sldId id="{255 + ordinal}" r:id="{relation_id}"/>'
        )
        presentation_relations.append(
            (relation_id, _OFFICE_REL + "slide", f"slides/{leaf}")
        )
        slide_part = f"ppt/slides/{leaf}"
        parts[slide_part] = _xml(
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld>{_ppt_sp_tree(f"Bounded slide {ordinal:03d}")}</p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
        )
        parts[f"ppt/slides/_rels/{leaf}.rels"] = _relationship_part(
            (
                (
                    "rId1",
                    _OFFICE_REL + "slideLayout",
                    "../slideLayouts/slideLayout1.xml",
                ),
            )
        )
        overrides.append(
            (
                slide_part,
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
            )
        )
    presentation_relations.append(
        (
            f"rId{slide_count + 2}",
            _OFFICE_REL + "presProps",
            "presProps.xml",
        )
    )
    parts.update(
        {
            "ppt/_rels/presentation.xml.rels": _relationship_part(
                presentation_relations
            ),
            "ppt/presProps.xml": _xml(
                '<p:presentationPr xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'
            ),
            "ppt/presentation.xml": _xml(
                '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                "<p:sldIdLst>"
                + "".join(slide_ids)
                + '</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/>'
                '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
            ),
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _relationship_part(
                (
                    (
                        "rId1",
                        _OFFICE_REL + "slideMaster",
                        "../slideMasters/slideMaster1.xml",
                    ),
                )
            ),
            "ppt/slideLayouts/slideLayout1.xml": _xml(
                '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">'
                f'<p:cSld name="Blank">{_ppt_sp_tree()}</p:cSld>'
                '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
            ),
            "ppt/slideMasters/_rels/slideMaster1.xml.rels": _relationship_part(
                (
                    (
                        "rId1",
                        _OFFICE_REL + "slideLayout",
                        "../slideLayouts/slideLayout1.xml",
                    ),
                    (
                        "rId2",
                        _OFFICE_REL + "theme",
                        "../theme/theme1.xml",
                    ),
                )
            ),
            "ppt/slideMasters/slideMaster1.xml": _xml(
                '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                f"<p:cSld>{_ppt_sp_tree()}</p:cSld>"
                '<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
                'accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" '
                'hlink="hlink" tx1="dk1" tx2="dk2"/>'
                '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
                '<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>'
            ),
            "ppt/theme/theme1.xml": _expected_ppt_theme(),
        }
    )
    overrides.extend(
        (
            (
                "docProps/core.xml",
                "application/vnd.openxmlformats-package.core-properties+xml",
            ),
            (
                "docProps/app.xml",
                "application/vnd.openxmlformats-officedocument.extended-properties+xml",
            ),
        )
    )
    parts["[Content_Types].xml"] = _content_types(overrides)
    return parts


def _expected_parts_for(variant, complexity):
    if variant == "docx":
        return _expected_docx_parts(complexity)
    if variant == "xlsx":
        return _expected_xlsx_parts(complexity)
    if variant == "pptx":
        return _expected_pptx_parts(complexity)
    _fail("unsupported expected OOXML template")


def _assemble_expected_zip(parts):
    local = bytearray()
    central_rows = []
    for name in sorted(parts):
        _safe_member_name(name)
        payload = parts[name]
        if type(payload) is not bytes or len(payload) > MAX_XML_PART_BYTES:
            _fail("expected OOXML part is not bounded bytes")
        name_bytes = name.encode("ascii")
        crc32 = zlib.crc32(payload) & 0xFFFFFFFF
        local_offset = len(local)
        local.extend(
            _LOCAL_FILE_HEADER.pack(
                _LOCAL_FILE_SIGNATURE,
                ZIP_EXTRACT_VERSION,
                0,
                0,
                ZIP_DOS_TIME,
                ZIP_DOS_DATE,
                crc32,
                len(payload),
                len(payload),
                len(name_bytes),
                0,
            )
        )
        local.extend(name_bytes)
        local.extend(payload)
        central_rows.append((name_bytes, crc32, len(payload), local_offset))
    central_offset = len(local)
    central = bytearray()
    for name_bytes, crc32, payload_length, local_offset in central_rows:
        central.extend(
            _CENTRAL_DIRECTORY_HEADER.pack(
                _CENTRAL_DIRECTORY_SIGNATURE,
                ZIP_CREATOR_VERSION,
                ZIP_EXTRACT_VERSION,
                0,
                0,
                ZIP_DOS_TIME,
                ZIP_DOS_DATE,
                crc32,
                payload_length,
                payload_length,
                len(name_bytes),
                0,
                0,
                0,
                0,
                ZIP_EXTERNAL_ATTRIBUTES,
                local_offset,
            )
        )
        central.extend(name_bytes)
    end = _END_OF_CENTRAL_DIRECTORY.pack(
        _END_OF_CENTRAL_DIRECTORY_SIGNATURE,
        0,
        0,
        len(central_rows),
        len(central_rows),
        len(central),
        central_offset,
        0,
    )
    return bytes(local + central + end)


def _expected_ooxml(variant, complexity, target_bytes):
    parts = _expected_parts_for(variant, complexity)
    padding_length = target_bytes - len(_assemble_expected_zip(parts))
    if padding_length < 0:
        _fail("OOXML skeleton exceeds its affine target")
    parts["docProps/core.xml"] = _core_properties(padding_length)
    data = _assemble_expected_zip(parts)
    if len(data) != target_bytes:
        _fail("expected OOXML padding formula drifted")
    return data


def _parse_bounded_xml(name, payload):
    if type(payload) is not bytes or not payload or len(payload) > MAX_XML_PART_BYTES:
        _fail(f"OOXML XML part is outside byte bounds: {name}")
    if not payload.startswith(_XML_DECLARATION_BYTES) or not payload.endswith(b"\n"):
        _fail(f"OOXML XML declaration/newline drifted: {name}")
    lowered = payload.lower()
    for token in (b"<!doctype", b"<!entity", b" system ", b" public ", b"xi:include"):
        if token in lowered:
            _fail(f"OOXML XML contains a forbidden construct: {name}")
    if payload.count(b"<?") != 1:
        _fail(f"OOXML XML contains an extra processing instruction: {name}")
    depth = 0
    maximum_depth = 0
    element_count = 0
    try:
        parser = ET.iterparse(io.BytesIO(payload), events=("start", "end"))
        for event, _element in parser:
            if event == "start":
                depth += 1
                maximum_depth = max(maximum_depth, depth)
                element_count += 1
                if maximum_depth > MAX_XML_DEPTH:
                    _fail(f"OOXML XML nesting exceeds {MAX_XML_DEPTH}: {name}")
                if element_count > MAX_XML_ELEMENTS:
                    _fail(f"OOXML XML element count exceeds {MAX_XML_ELEMENTS}: {name}")
            else:
                depth -= 1
        root = parser.root
    except ET.ParseError:
        _fail(f"OOXML XML is not well formed: {name}")
    if depth != 0 or root is None:
        _fail(f"OOXML XML parse did not close exactly: {name}")
    return root


def _relationship_source(rels_name):
    if rels_name == "_rels/.rels":
        return ""
    directory, leaf = posixpath.split(rels_name)
    if posixpath.basename(directory) != "_rels" or not leaf.endswith(".rels"):
        _fail("OOXML relationship part path is malformed")
    parent = posixpath.dirname(directory)
    return posixpath.join(parent, leaf[:-5])


def _validate_content_types(parts, roots):
    name = "[Content_Types].xml"
    if name not in roots:
        _fail("OOXML package lacks [Content_Types].xml")
    namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    root = roots[name]
    if root.tag != f"{{{namespace}}}Types" or root.attrib:
        _fail("OOXML content-types root drifted")
    defaults = {}
    overrides = {}
    for child in root:
        if child.tag == f"{{{namespace}}}Default":
            if set(child.attrib) != {"Extension", "ContentType"}:
                _fail("OOXML Default content type attributes drifted")
            extension = child.attrib["Extension"]
            if extension in defaults:
                _fail("OOXML content types contain a duplicate Default")
            defaults[extension] = child.attrib["ContentType"]
        elif child.tag == f"{{{namespace}}}Override":
            if set(child.attrib) != {"PartName", "ContentType"}:
                _fail("OOXML Override content type attributes drifted")
            part_name = child.attrib["PartName"]
            if not part_name.startswith("/"):
                _fail("OOXML Override PartName is not package absolute")
            target = part_name[1:]
            _safe_member_name(target)
            if target in overrides or target not in parts:
                _fail("OOXML content type override is duplicate or dangling")
            overrides[target] = child.attrib["ContentType"]
        else:
            _fail("OOXML content types contain an unknown child")
    if defaults != {
        "rels": "application/vnd.openxmlformats-package.relationships+xml",
        "xml": "application/xml",
    }:
        _fail("OOXML Default content types drifted")
    for part_name in parts:
        if part_name in {name} or part_name.endswith(".rels"):
            continue
        if part_name not in overrides and not part_name.endswith(".xml"):
            _fail("OOXML part has no bounded content-type mapping")


def _validate_relationships(parts, roots):
    relationships_by_source = {}
    for rels_name in sorted(name for name in parts if name.endswith(".rels")):
        source = _relationship_source(rels_name)
        if source and source not in parts:
            _fail("OOXML relationship source part is missing")
        root = roots[rels_name]
        if root.tag != f"{{{_REL_NS}}}Relationships" or root.attrib:
            _fail("OOXML relationship root drifted")
        relation_ids = set()
        targets = []
        base = posixpath.dirname(source)
        for relation in root:
            if relation.tag != f"{{{_REL_NS}}}Relationship":
                _fail("OOXML relationship part contains an unknown child")
            if set(relation.attrib) != {"Id", "Type", "Target"}:
                _fail("OOXML relationship attributes drifted or are external")
            relation_id = relation.attrib["Id"]
            relation_type = relation.attrib["Type"]
            target = relation.attrib["Target"]
            if (
                not relation_id
                or relation_id in relation_ids
                or not relation_id.isascii()
                or not relation_type.isascii()
                or not target.isascii()
                or not relation_type.startswith(
                    "http://schemas.openxmlformats.org/"
                )
                or not target
                or target.startswith("/")
                or "\\" in target
                or ":" in target
                or "%" in target
                or "?" in target
                or "#" in target
            ):
                _fail("OOXML relationship ID/type/target is unsafe")
            lowered = (relation_type + target).lower().encode("ascii")
            if any(token in lowered for token in _FORBIDDEN_OOXML_TOKENS):
                _fail("OOXML relationship references active content")
            resolved = posixpath.normpath(posixpath.join(base, target))
            if resolved.startswith("../") or resolved not in parts:
                _fail("OOXML relationship target is missing or escapes package")
            relation_ids.add(relation_id)
            targets.append((relation_id, relation_type, resolved))
        relationships_by_source[source] = targets

    if "" not in relationships_by_source:
        _fail("OOXML root relationship part is missing")
    reachable = {""}
    frontier = [""]
    while frontier:
        source = frontier.pop()
        for _relation_id, _relation_type, target in relationships_by_source.get(
            source, ()
        ):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    semantic_parts = {
        name
        for name in parts
        if name != "[Content_Types].xml" and not name.endswith(".rels")
    }
    if not semantic_parts <= reachable:
        _fail("OOXML package contains an orphan semantic part")
    return relationships_by_source


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _validate_docx_structure(parts, roots, complexity):
    document = roots.get("word/document.xml")
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    if document is None or document.tag != f"{{{namespace}}}document":
        _fail("DOCX main document root drifted")
    body = document.find(f"{{{namespace}}}body")
    if body is None or body is not list(document)[-1]:
        _fail("DOCX body is missing or misplaced")
    sections = list(document.iter(f"{{{namespace}}}sectPr"))
    labels = [
        element.text
        for element in document.iter(f"{{{namespace}}}t")
        if element.text and element.text.startswith("Bounded section ")
    ]
    if len(sections) != complexity or len(labels) != complexity:
        _fail("DOCX section complexity count drifted")
    if not list(body) or list(body)[-1].tag != f"{{{namespace}}}sectPr":
        _fail("DOCX final section properties are not the final body child")


def _validate_xlsx_structure(parts, roots, complexity):
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    workbook = roots.get("xl/workbook.xml")
    if workbook is None or workbook.tag != f"{{{namespace}}}workbook":
        _fail("XLSX workbook root drifted")
    sheets_parent = workbook.find(f"{{{namespace}}}sheets")
    sheets = [] if sheets_parent is None else list(sheets_parent)
    if len(sheets) != complexity:
        _fail("XLSX workbook sheet complexity count drifted")
    names = []
    identifiers = []
    relationship_ids = []
    for sheet in sheets:
        if sheet.tag != f"{{{namespace}}}sheet":
            _fail("XLSX sheets contain an unknown child")
        names.append(sheet.attrib.get("name"))
        identifiers.append(sheet.attrib.get("sheetId"))
        relationship_ids.append(sheet.attrib.get(f"{{{relationship_namespace}}}id"))
    if (
        len(set(names)) != complexity
        or len(set(identifiers)) != complexity
        or len(set(relationship_ids)) != complexity
    ):
        _fail("XLSX sheet names, IDs, or relationships are not unique")
    worksheet_names = sorted(
        name for name in parts if name.startswith("xl/worksheets/sheet")
    )
    if len(worksheet_names) != complexity:
        _fail("XLSX worksheet part count drifted")
    for name in worksheet_names:
        root = roots[name]
        if root.tag != f"{{{namespace}}}worksheet":
            _fail("XLSX worksheet root drifted")
        if list(root.iter(f"{{{namespace}}}f")):
            _fail("XLSX formula content is forbidden")
        cells = list(root.iter(f"{{{namespace}}}c"))
        if len(cells) != 1 or cells[0].attrib.get("r") != "A1":
            _fail("XLSX worksheet must contain one exact A1 cell")


def _relationship_targets(relationships, source, relation_suffix):
    return {
        target
        for _relation_id, relation_type, target in relationships.get(source, ())
        if relation_type == _OFFICE_REL + relation_suffix
    }


def _validate_pptx_structure(parts, roots, relationships, complexity):
    namespace = "http://schemas.openxmlformats.org/presentationml/2006/main"
    relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    presentation = roots.get("ppt/presentation.xml")
    if presentation is None or presentation.tag != f"{{{namespace}}}presentation":
        _fail("PPTX presentation root drifted")
    identifiers = list(presentation.iter(f"{{{namespace}}}sldId"))
    if len(identifiers) != complexity:
        _fail("PPTX slide complexity count drifted")
    numeric_ids = [element.attrib.get("id") for element in identifiers]
    relation_ids = [
        element.attrib.get(f"{{{relationship_namespace}}}id")
        for element in identifiers
    ]
    if len(set(numeric_ids)) != complexity or len(set(relation_ids)) != complexity:
        _fail("PPTX slide identifiers are not unique")
    slides = sorted(
        name
        for name in parts
        if name.startswith("ppt/slides/slide") and name.endswith(".xml")
    )
    slide_relationships = sorted(
        name
        for name in parts
        if name.startswith("ppt/slides/_rels/slide") and name.endswith(".xml.rels")
    )
    if len(slides) != complexity or len(slide_relationships) != complexity:
        _fail("PPTX slide or slide-relationship part count drifted")
    if "ppt/presProps.xml" not in parts:
        _fail("PPTX lacks the required presentation-properties part")
    if _relationship_targets(
        relationships, "ppt/presentation.xml", "presProps"
    ) != {"ppt/presProps.xml"}:
        _fail("PPTX presentation-properties relationship drifted")
    if _relationship_targets(
        relationships, "ppt/presentation.xml", "slideMaster"
    ) != {"ppt/slideMasters/slideMaster1.xml"}:
        _fail("PPTX presentation-to-master relationship drifted")
    if _relationship_targets(
        relationships, "ppt/slideMasters/slideMaster1.xml", "slideLayout"
    ) != {"ppt/slideLayouts/slideLayout1.xml"}:
        _fail("PPTX master-to-layout relationship drifted")
    if _relationship_targets(
        relationships, "ppt/slideMasters/slideMaster1.xml", "theme"
    ) != {"ppt/theme/theme1.xml"}:
        _fail("PPTX master-to-theme relationship drifted")
    if _relationship_targets(
        relationships, "ppt/slideLayouts/slideLayout1.xml", "slideMaster"
    ) != {"ppt/slideMasters/slideMaster1.xml"}:
        _fail("PPTX layout-to-master relationship drifted")
    for slide in slides:
        if roots[slide].tag != f"{{{namespace}}}sld":
            _fail("PPTX slide root drifted")
        if _relationship_targets(relationships, slide, "slideLayout") != {
            "ppt/slideLayouts/slideLayout1.xml"
        }:
            _fail("PPTX slide-to-layout relationship drifted")


def _validate_ooxml_structure(variant, data, complexity):
    lowered = data.lower()
    if any(token in lowered for token in _FORBIDDEN_OOXML_TOKENS):
        _fail("OOXML contains a forbidden macro/OLE/external feature")
    parts = _parse_bounded_stored_zip(data)
    required = {"[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "docProps/app.xml"}
    if not required <= set(parts):
        _fail("OOXML package lacks required common parts")
    if any(not name.endswith((".xml", ".rels")) for name in parts):
        _fail("OOXML package contains a non-XML binary member")
    roots = {
        name: _parse_bounded_xml(name, payload) for name, payload in parts.items()
    }
    _validate_content_types(parts, roots)
    relationships = _validate_relationships(parts, roots)
    if variant == "docx":
        _validate_docx_structure(parts, roots, complexity)
    elif variant == "xlsx":
        _validate_xlsx_structure(parts, roots, complexity)
    elif variant == "pptx":
        _validate_pptx_structure(parts, roots, relationships, complexity)
    else:  # pragma: no cover - exact variant table prevents this branch.
        _fail("unknown OOXML structure validator")
    return len(parts)


def validate_raw_document_payload(request):
    """Validate bounded bytes and return a strictly negative-authority receipt."""

    profile, target_bytes = _validate_request_shape(request)
    if request.variant == "pdf-scan":
        _validate_pdf_structure(request.data, request.target_complexity)
        expected = _expected_pdf(request.target_complexity, target_bytes)
        member_count = 0
        pdf_text_layer_absent = True
        zip_stored_validated = False
    else:
        member_count = _validate_ooxml_structure(
            request.variant, request.data, request.target_complexity
        )
        expected = _expected_ooxml(
            request.variant, request.target_complexity, target_bytes
        )
        pdf_text_layer_absent = False
        zip_stored_validated = True
    if request.data != expected:
        _fail("payload differs from independent exact-byte regeneration")
    return {
        "actual_chunks_attested": False,
        "byte_length": len(request.data),
        "container_member_count": member_count,
        "identity_tokens_absent": True,
        "kio_execution_attested": False,
        "observed_complexity_measure": profile["complexity_measure"],
        "observed_local_complexity": request.target_complexity,
        "pdf_text_layer_absent": pdf_text_layer_absent,
        "structure_validated": True,
        "target_bytes": target_bytes,
        "zip_stored_validated": zip_stored_validated,
    }


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    minimum = profile["inclusive_minimum"]
    maximum = profile["inclusive_maximum"]
    return {
        "complexity": {
            "counting_rule": _COMPLEXITY_COUNTING_RULES[variant],
            "inclusive_maximum": maximum,
            "inclusive_minimum": minimum,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kio_path_media_type": profile["expected_kio_path_media_type"],
        "expected_offline_disposition": profile["expected_offline_disposition"],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": "raw_only",
        "raw_byte_formula": {
            "base_bytes_at_minimum_complexity": profile["base_bytes"],
            "increment_bytes_per_additional_complexity": profile["increment_bytes"],
            "maximum_rendered_bytes": target_bytes_for(variant, maximum),
            "minimum_complexity": minimum,
            "minimum_rendered_bytes": target_bytes_for(variant, minimum),
            "selection_phase": "solved-source-recipe-instance-not-this-contract",
        },
        "render_template": profile["render_template"],
        "validator_profile_id": (
            f"{variant}-standalone-id-free-raw-document-validation-v2"
        ),
        "variant_id": variant,
    }


def _canonical_contract_value():
    return {
        "artifact_kind": CONTRACT_KIND,
        "artifact_schema": CONTRACT_SCHEMA,
        "artifact_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_final_source_identifiers": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_renderer_execution": False,
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "kio_execution_attested": False,
        },
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_ooxml_members": MAX_ZIP_MEMBERS,
            "max_pdf_non_stream_line_bytes": MAX_PDF_NON_STREAM_LINE_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "max_xml_depth": MAX_XML_DEPTH,
            "max_xml_elements": MAX_XML_ELEMENTS,
            "max_xml_part_bytes": MAX_XML_PART_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "four-id-free-formal-ordinary-raw-document-validation-variants-only-"
            "not-byte-stress-source-materialization-or-kio-attestation"
        ),
        "independence_contract": {
            "imports_planning_modules": False,
            "imports_renderer_module": False,
            "imports_source_or_variant_catalog": False,
            "parses_pdf_xref_and_objects_with_bounded_primitives": True,
            "parses_zip_headers_before_member_payloads": True,
            "parses_xml_with_depth_and_element_bounds": True,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_target_byte_formula": True,
        },
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
    }


def build_validator_contract():
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw-document validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw-document validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free raw-document validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentValidatorError(str(error)) from None


__all__ = [
    "FIXED_ZIP_EPOCH",
    "MAX_PDF_NON_STREAM_LINE_BYTES",
    "MAX_RENDERED_BYTES",
    "MAX_XML_DEPTH",
    "MAX_XML_ELEMENTS",
    "MAX_XML_PART_BYTES",
    "MAX_ZIP_MEMBERS",
    "PersonaV2RawDocumentValidatorError",
    "READY_VARIANTS",
    "RawDocumentValidationRequest",
    "VALIDATOR_ID",
    "build_validator_contract",
    "canonical_json_bytes",
    "target_bytes_for",
    "validate_raw_document_payload",
    "validate_validator_contract",
    "validator_contract_sha256",
]
