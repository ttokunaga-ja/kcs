"""Deterministic ID-free feasibility renderer for four raw document variants.

This vertical slice covers only ``pdf-scan``, ``docx``, ``xlsx``, and
``pptx`` in the formal ordinary (at most 512 KiB) lane.  Requests carry no
persona, source, path, query, digest, or history identity.  Rendering proves
only that bounded canonical bytes can be produced; it grants no source-plan,
physical-write, KCS, chunk, history, solver, or G0 authority.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import struct
import zlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kcs.persona.pc-id-free-raw-document-renderer/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-raw-document-renderer"
RENDERER_ID = "persona-v2-id-free-raw-document-feasibility-renderer"
RENDERER_SCHEMA_VERSION = 2

MAX_CONTRACT_BYTES = 96 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_PDF_NON_STREAM_LINE_BYTES = 255
MAX_ZIP_MEMBERS = 128
MAX_XML_PART_BYTES = 512 * 1024
FIXED_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
ZIP_CREATOR_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_DOS_TIME = 0
ZIP_DOS_DATE = 33  # 1980-01-01
ZIP_EXTERNAL_ATTRIBUTES = 0x20  # MS-DOS archive bit.

READY_VARIANTS = ("docx", "pdf-scan", "pptx", "xlsx")

REQUEST_FIELDS = ("schema_version", "variant", "target_complexity")

PROHIBITED_IDENTITY_FIELDS = (
    "answer",
    "chunk",
    "digest",
    "final_source_id",
    "fixture_nonce",
    "intent_key",
    "materialization_id",
    "oracle",
    "path",
    "persona_id",
    "query",
    "raw_hash",
    "scope_key",
    "solution",
    "source_id",
)

_VARIANT_ROWS = {
    "docx": {
        "base_bytes": 8_192,
        "complexity_measure": "document-sections",
        "content_media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "expected_kcs_path_media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
        "expected_kcs_path_media_type": "application/pdf",
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
        "expected_kcs_path_media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
        "expected_kcs_path_media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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


class PersonaV2RawDocumentRendererError(ValueError):
    """Raised when the raw-document renderer contract is violated."""


@dataclass(frozen=True, slots=True)
class RawDocumentRenderRequest:
    """An intentionally identity-free local feasibility request."""

    schema_version: int
    variant: str
    target_complexity: int


@dataclass(frozen=True, slots=True)
class RenderedRawDocument:
    """Rendered bytes and non-authoritative format metadata."""

    data: bytes
    extension: str
    content_media_type: str
    expected_kcs_path_media_type: str
    expected_offline_disposition: str
    target_complexity: int
    target_bytes: int
    renderer_id: str = RENDERER_ID
    renderer_schema_version: int = RENDERER_SCHEMA_VERSION


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        raise PersonaV2RawDocumentRendererError(
            "unsupported raw document variant"
        )
    return _VARIANT_ROWS[variant]


def validate_request(request):
    if type(request) is not RawDocumentRenderRequest:
        raise PersonaV2RawDocumentRendererError(
            "request must be an exact RawDocumentRenderRequest"
        )
    if tuple(RawDocumentRenderRequest.__dataclass_fields__) != REQUEST_FIELDS:
        raise PersonaV2RawDocumentRendererError("renderer request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        raise PersonaV2RawDocumentRendererError(
            "renderer request exposes an identity field"
        )
    if type(request.schema_version) is not int or request.schema_version != 2:
        raise PersonaV2RawDocumentRendererError(
            "renderer request schema version must be exact 2"
        )
    profile = _profile(request.variant)
    if (
        type(request.target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= request.target_complexity
        <= profile["inclusive_maximum"]
    ):
        raise PersonaV2RawDocumentRendererError(
            "target complexity is outside the exact variant domain"
        )
    return True


def target_bytes_for(variant, target_complexity):
    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= target_complexity
        <= profile["inclusive_maximum"]
    ):
        raise PersonaV2RawDocumentRendererError(
            "target complexity is outside the exact variant domain"
        )
    target = profile["base_bytes"] + (
        target_complexity - profile["inclusive_minimum"]
    ) * profile["increment_bytes"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        raise PersonaV2RawDocumentRendererError(
            "target-byte formula exceeds the renderer cap"
        )
    return target


def _scan_pixels(page_number):
    return bytes((page_number * 17 + offset) % 251 for offset in range(256))


def _pdf_objects(page_count):
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
        pixels = _scan_pixels(page_number)
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width 16 /Height 16 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 256 >>\n"
            b"stream\n"
            + pixels
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


def _pdf_padding_comments(length):
    if type(length) is not int or length < 2:
        raise PersonaV2RawDocumentRendererError(
            "PDF padding comment must be at least two bytes"
        )
    full_records, remainder = divmod(length, MAX_PDF_NON_STREAM_LINE_BYTES + 1)
    record_lengths = [MAX_PDF_NON_STREAM_LINE_BYTES + 1] * full_records
    if remainder == 1:
        if not record_lengths:
            raise PersonaV2RawDocumentRendererError(
                "PDF padding cannot encode a one-byte comment"
            )
        record_lengths[-1] -= 1
        record_lengths.append(2)
    elif remainder:
        record_lengths.append(remainder)
    return b"".join(
        b"%" + _PDF_PADDING_BYTE * (record_length - 2) + b"\n"
        for record_length in record_lengths
    )


def _assemble_pdf(objects, padding_length):
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
        output.extend(_pdf_padding_comments(padding_length))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        if offset > 9_999_999_999:
            raise PersonaV2RawDocumentRendererError(
                "PDF object offset exceeds xref width"
            )
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _render_pdf(page_count, target_bytes):
    objects = _pdf_objects(page_count)
    padding_length = target_bytes - len(_assemble_pdf(objects, 0))
    if padding_length < 2:
        raise PersonaV2RawDocumentRendererError(
            "affine target leaves no valid PDF padding comment"
        )
    for _ in range(8):
        data = _assemble_pdf(objects, padding_length)
        delta = target_bytes - len(data)
        if delta == 0:
            return data
        padding_length += delta
        if padding_length < 2:
            break
    raise PersonaV2RawDocumentRendererError(
        "could not satisfy exact affine PDF byte formula"
    )


def _xml(body):
    if type(body) is not str or not body.isascii():
        raise PersonaV2RawDocumentRendererError("OOXML body must be exact ASCII")
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
        raise PersonaV2RawDocumentRendererError(
            "OOXML core-property padding must be a non-negative integer"
        )
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


def _docx_parts(section_count):
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


def _xlsx_styles():
    return _xml(
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>'
    )


def _xlsx_parts(worksheet_count):
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
            "xl/styles.xml": _xlsx_styles(),
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


def _ppt_theme():
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


def _pptx_parts(slide_count):
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
            "ppt/theme/theme1.xml": _ppt_theme(),
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


def _parts_for(variant, complexity):
    if variant == "docx":
        return _docx_parts(complexity)
    if variant == "xlsx":
        return _xlsx_parts(complexity)
    if variant == "pptx":
        return _pptx_parts(complexity)
    raise PersonaV2RawDocumentRendererError("unsupported OOXML render template")


def _safe_part_name(name):
    if (
        type(name) is not str
        or not name
        or not name.isascii()
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or "\x00" in name
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise PersonaV2RawDocumentRendererError("unsafe OOXML member path")


def _zip_package(parts):
    if type(parts) is not dict or not 1 <= len(parts) <= MAX_ZIP_MEMBERS:
        raise PersonaV2RawDocumentRendererError("OOXML member count is out of bounds")
    local = bytearray()
    central_rows = []
    for name in sorted(parts):
        _safe_part_name(name)
        payload = parts[name]
        if type(payload) is not bytes or len(payload) > MAX_XML_PART_BYTES:
            raise PersonaV2RawDocumentRendererError(
                "OOXML part is not bounded exact bytes"
            )
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
    if len(central_rows) > 0xFFFF:
        raise PersonaV2RawDocumentRendererError("OOXML exceeds classic ZIP count")
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


def _render_ooxml(variant, complexity, target_bytes):
    parts = _parts_for(variant, complexity)
    unpadded = _zip_package(parts)
    padding_length = target_bytes - len(unpadded)
    if padding_length < 0:
        raise PersonaV2RawDocumentRendererError(
            "OOXML skeleton exceeds its affine target"
        )
    parts["docProps/core.xml"] = _core_properties(padding_length)
    data = _zip_package(parts)
    if len(data) != target_bytes:
        raise PersonaV2RawDocumentRendererError(
            "OOXML stored-package padding formula drifted"
        )
    return data


def render_raw_document(request):
    """Render one deterministic local exemplar without source identity."""

    validate_request(request)
    profile = _profile(request.variant)
    target_bytes = target_bytes_for(request.variant, request.target_complexity)
    if request.variant == "pdf-scan":
        data = _render_pdf(request.target_complexity, target_bytes)
    else:
        data = _render_ooxml(
            request.variant, request.target_complexity, target_bytes
        )
    if type(data) is not bytes or len(data) != target_bytes:
        raise PersonaV2RawDocumentRendererError(
            "rendered payload differs from exact byte formula"
        )
    return RenderedRawDocument(
        data=data,
        extension=profile["filename_extension"],
        content_media_type=profile["content_media_type"],
        expected_kcs_path_media_type=profile["expected_kcs_path_media_type"],
        expected_offline_disposition=profile["expected_offline_disposition"],
        target_complexity=request.target_complexity,
        target_bytes=target_bytes,
    )


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
        "expected_kcs_path_media_type": profile["expected_kcs_path_media_type"],
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
            "kcs_execution_attested": False,
        },
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_ooxml_members": MAX_ZIP_MEMBERS,
            "max_pdf_non_stream_line_bytes": MAX_PDF_NON_STREAM_LINE_BYTES,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "max_xml_part_bytes": MAX_XML_PART_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "four-id-free-formal-ordinary-raw-document-feasibility-variants-only-"
            "not-byte-stress-source-materialization-or-kcs-attestation"
        ),
        "payload_identity_policy": {
            "content_digest_embedded": False,
            "final_source_identifier_embedded": False,
            "intent_identifier_embedded": False,
            "materialization_identifier_embedded": False,
            "persona_identifier_embedded": False,
            "query_or_oracle_content_embedded": False,
            "scope_identifier_embedded": False,
            "source_identifier_embedded": False,
        },
        "renderer_id": RENDERER_ID,
        "renderer_schema_version": RENDERER_SCHEMA_VERSION,
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
    }


def build_renderer_contract():
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free raw-document renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentRendererError(str(error)) from None


def validate_renderer_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw-document renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentRendererError(str(error)) from None


def renderer_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_renderer_contract,
            label="persona v2 ID-free raw-document renderer contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RawDocumentRendererError(str(error)) from None


__all__ = [
    "FIXED_ZIP_EPOCH",
    "MAX_PDF_NON_STREAM_LINE_BYTES",
    "MAX_RENDERED_BYTES",
    "MAX_XML_PART_BYTES",
    "MAX_ZIP_MEMBERS",
    "PersonaV2RawDocumentRendererError",
    "READY_VARIANTS",
    "RENDERER_ID",
    "RawDocumentRenderRequest",
    "RenderedRawDocument",
    "build_renderer_contract",
    "canonical_json_bytes",
    "render_raw_document",
    "renderer_contract_sha256",
    "target_bytes_for",
    "validate_renderer_contract",
    "validate_request",
]
