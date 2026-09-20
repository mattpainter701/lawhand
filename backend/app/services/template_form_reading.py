"""Read a printed, hand-filled copy of a form against the template it came from.

A firm sends a client a PDF form generated from one of its templates. The
client prints it, fills it in by hand, and sends back a scan. The scan has no
AcroForm values and its handwriting sits exactly where the template put each
field. Because the generating template version is known (the matter's
``document_generated`` event names it) and the published version records every
field's page and rectangle, the scan does not need to be understood as a
whole: each field's rectangle is cut out of the scanned page and read on its
own, giving a value per field with the confidence it was read at and a
thumbnail of the handwriting for the reviewer.

This module is pure: it takes bytes and the field windows and returns
readings. It never touches a matter, never writes, and the OCR call is
injectable so the geometry can be tested without an OCR runtime.

Version 1 alignment is by page size only: the scan is assumed to be the same
page, scaled. A skewed or cropped scan reads badly and says so through low
confidence; deskew and feature alignment are a follow-up.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any, Callable

from app.services.template_fill_coverage import is_signing_field
from app.services.template_ocr import TemplateOcrError, image_to_pdf, ocr_image

MAX_WINDOWS = 200
MAX_THUMBNAILS = 60
THUMBNAIL_WIDTH = 200
RENDER_SCALE = 2.0
CROP_MARGIN_PT = 4.0
MAX_RENDERED_PIXELS = 40_000_000
ALIGNMENT = "scaled"


@dataclass(frozen=True)
class FieldWindow:
    name: str
    label: str
    page: int  # 1-based
    rect: tuple[float, float, float, float]  # PDF points, [x0, y0, x1, y1]
    binding: str | None = None


@dataclass
class FieldReading:
    name: str
    label: str
    page: int
    rect: tuple[float, float, float, float]
    text: str
    confidence: float
    thumbnail_png_b64: str | None = None
    binding: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "binding": self.binding,
            "page": self.page,
            "rect": [round(value, 2) for value in self.rect],
            "text": self.text,
            "confidence": self.confidence,
            "thumbnail_png_b64": self.thumbnail_png_b64,
        }


def _rect_of(spec: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(spec, (list, tuple)) or len(spec) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(value) for value in spec)
    except (TypeError, ValueError):
        return None
    left, right = sorted((x0, x1))
    bottom, top = sorted((y0, y1))
    if right - left < 1 or top - bottom < 1:
        return None
    return (left, bottom, right, top)


def field_windows(schema: dict | None) -> list[FieldWindow]:
    """Every fillable field of a published version that has a place on a page."""

    windows: list[FieldWindow] = []
    for field in (schema or {}).get("fields", []) or []:
        if not isinstance(field, dict) or field.get("included") is False:
            continue
        name = str(field.get("name") or "").strip()
        if not name or is_signing_field(field) or field.get("value_from"):
            continue
        overlay = (
            field.get("pdf_overlay")
            if isinstance(field.get("pdf_overlay"), dict)
            else {}
        )
        page = overlay.get("page") or field.get("page")
        rect = _rect_of(overlay.get("rect") or field.get("rect"))
        try:
            page_no = int(page)
        except (TypeError, ValueError):
            continue
        if page_no < 1 or rect is None:
            continue
        windows.append(
            FieldWindow(
                name=name,
                label=str(field.get("label") or name),
                page=page_no,
                rect=rect,
                binding=str(field.get("binding") or "") or None,
            )
        )
        if len(windows) >= MAX_WINDOWS:
            break
    return windows


def _png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _thumbnail(image) -> str:
    from PIL import Image

    copy = image.copy()
    if copy.width > THUMBNAIL_WIDTH:
        ratio = THUMBNAIL_WIDTH / copy.width
        copy = copy.resize(
            (THUMBNAIL_WIDTH, max(1, int(copy.height * ratio))), Image.LANCZOS
        )
    try:
        return base64.b64encode(_png_bytes(copy)).decode("ascii")
    finally:
        copy.close()


def _default_ocr(png: bytes) -> tuple[str, float]:
    result = ocr_image(png)
    return result.text, float(result.average_confidence)


def normalize_scan(content: bytes, filename: str) -> bytes:
    """A scan as a PDF: images are rasterised the way OCR intake does."""

    if str(filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        return image_to_pdf(content).content
    return content


def read_scan(
    scan_pdf: bytes,
    windows: list[FieldWindow],
    *,
    template_page_sizes: dict[int, tuple[float, float]],
    ocr: Callable[[bytes], tuple[str, float]] | None = None,
    thumbnails: int = MAX_THUMBNAILS,
) -> list[FieldReading]:
    """Read each field window out of the scanned pages.

    ``template_page_sizes`` maps a 1-based page number to the template page's
    (width, height) in points; the scan's page is scaled to it. ``ocr`` takes
    PNG bytes of one crop and returns ``(text, confidence)``.
    """

    read = ocr or _default_ocr
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise TemplateOcrError(
            "PDF rendering is unavailable in this environment."
        ) from exc

    by_page: dict[int, list[FieldWindow]] = {}
    for window in windows[:MAX_WINDOWS]:
        by_page.setdefault(window.page, []).append(window)
    readings: list[FieldReading] = []
    thumbnails_left = max(0, int(thumbnails))
    remaining_pixels = MAX_RENDERED_PIXELS
    try:
        document = pdfium.PdfDocument(scan_pdf)
    except Exception as exc:
        raise TemplateOcrError("The scan could not be opened as a PDF.") from exc
    try:
        total = len(document)
        for page_no in sorted(by_page):
            if page_no > total:
                continue
            page = document[page_no - 1]
            image = None
            try:
                scan_w, scan_h = (float(value) for value in page.get_size())
                template_w, template_h = template_page_sizes.get(
                    page_no, (scan_w, scan_h)
                )
                if scan_w <= 0 or scan_h <= 0 or template_w <= 0 or template_h <= 0:
                    continue
                scale = RENDER_SCALE
                if scan_w * scan_h * scale * scale > remaining_pixels:
                    scale = max(1.0, (remaining_pixels / (scan_w * scan_h)) ** 0.5)
                if scan_w * scan_h * scale * scale > remaining_pixels:
                    break
                bitmap = page.render(scale=scale, rev_byteorder=True)
                try:
                    rendered = bitmap.to_pil()
                    image = (
                        rendered if rendered.mode == "RGB" else rendered.convert("RGB")
                    )
                finally:
                    bitmap.close()
                remaining_pixels -= image.width * image.height
                # Template points → scan points → rendered pixels. The y axis
                # flips: PDF measures from the bottom, the raster from the top.
                sx = scan_w / template_w * scale
                sy = scan_h / template_h * scale
                for window in by_page[page_no]:
                    left, bottom, right, top = window.rect
                    px0 = max(0, int((left - CROP_MARGIN_PT) * sx))
                    px1 = min(image.width, int((right + CROP_MARGIN_PT) * sx) + 1)
                    py0 = max(0, int((template_h - top - CROP_MARGIN_PT) * sy))
                    py1 = min(
                        image.height,
                        int((template_h - bottom + CROP_MARGIN_PT) * sy) + 1,
                    )
                    if px1 - px0 < 2 or py1 - py0 < 2:
                        continue
                    crop = image.crop((px0, py0, px1, py1))
                    try:
                        try:
                            text, confidence = read(_png_bytes(crop))
                        except TemplateOcrError:
                            text, confidence = "", 0.0
                        thumbnail = None
                        if thumbnails_left > 0:
                            thumbnail = _thumbnail(crop)
                            thumbnails_left -= 1
                    finally:
                        crop.close()
                    readings.append(
                        FieldReading(
                            name=window.name,
                            label=window.label,
                            page=page_no,
                            rect=window.rect,
                            text=" ".join(str(text or "").split()),
                            confidence=round(max(0.0, min(1.0, float(confidence))), 4),
                            thumbnail_png_b64=thumbnail,
                            binding=window.binding,
                        )
                    )
            finally:
                if image is not None:
                    image.close()
                page.close()
    finally:
        document.close()
    return readings


def page_sizes(pdf: bytes) -> dict[int, tuple[float, float]]:
    """1-based page number → (width, height) in points."""

    from pypdf import PdfReader

    sizes: dict[int, tuple[float, float]] = {}
    reader = PdfReader(io.BytesIO(pdf))
    for index, page in enumerate(reader.pages, 1):
        box = page.mediabox
        sizes[index] = (float(box.width), float(box.height))
    return sizes
