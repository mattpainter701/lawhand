"""The field-window reader: geometry in, readings out, no OCR runtime needed."""

from io import BytesIO

import pytest

from app.services import template_form_reading as reading
from app.services.pdf_templates import discover_pdf_fields
from tests.esign_pdf_fixtures import acroform_pdf


def _schema_from(pdf: bytes) -> dict:
    return {"fields": discover_pdf_fields(pdf)}


def test_field_windows_skip_signing_and_unplaced_fields():
    schema = {
        "fields": [
            {"name": "client_name", "label": "Client name", "page": 1, "rect": [150, 690, 350, 710]},
            {"name": "sig", "field_type": "signature", "signer_role": "client", "page": 1, "rect": [72, 90, 300, 130]},
            {"name": "derived", "value_from": "client_name", "page": 1, "rect": [1, 1, 50, 20]},
            {"name": "no_place", "label": "Nowhere"},
            {"name": "overlay", "pdf_overlay": {"page": 2, "rect": [10, 10, 100, 30]}, "binding": "client.email"},
            {"name": "bad_rect", "page": 1, "rect": [10, 10, 10, 10]},
            {"name": "excluded", "included": False, "page": 1, "rect": [10, 10, 60, 30]},
        ]
    }
    windows = reading.field_windows(schema)
    assert [window.name for window in windows] == ["client_name", "overlay"]
    assert windows[0].rect == (150.0, 690.0, 350.0, 710.0)
    assert windows[1].page == 2 and windows[1].binding == "client.email"


def test_read_scan_crops_each_window_where_the_template_put_it():
    pdf = acroform_pdf()
    windows = reading.field_windows(_schema_from(pdf))
    names = [window.name for window in windows]
    assert "client_name" in names and "client_signature" not in names
    sizes = reading.page_sizes(pdf)
    assert sizes[1] == pytest.approx((612.0, 792.0))

    crops = []

    def fake_ocr(png: bytes):
        from PIL import Image

        with Image.open(BytesIO(png)) as image:
            crops.append(image.size)
        return f"read {len(crops)}", 0.5 + 0.1 * len(crops)

    readings = reading.read_scan(pdf, windows, template_page_sizes=sizes, ocr=fake_ocr, thumbnails=1)
    assert [item.name for item in readings] == names
    client = next(item for item in readings if item.name == "client_name")
    # The widget is 200 x 20 pt at scale 2 with a 4 pt margin each side.
    width, height = crops[names.index("client_name")]
    assert 410 <= width <= 420 and 50 <= height <= 60
    assert client.text == f"read {names.index('client_name') + 1}"
    assert 0 < client.confidence <= 1
    assert client.page == 1 and client.rect == windows[names.index("client_name")].rect
    # One thumbnail was asked for; the rest carry none.
    assert sum(1 for item in readings if item.thumbnail_png_b64) == 1
    assert readings[0].thumbnail_png_b64
    assert readings[0].as_dict()["rect"] == [round(v, 2) for v in readings[0].rect]


def test_read_scan_scales_a_window_to_the_scanned_page_size():
    pdf = acroform_pdf()
    windows = [w for w in reading.field_windows(_schema_from(pdf)) if w.name == "client_name"]
    crops = []

    def fake_ocr(png: bytes):
        from PIL import Image

        with Image.open(BytesIO(png)) as image:
            crops.append(image.size)
        return "", 0.0

    # The template claims a page twice the scan's size, so the same window
    # covers half as many scan pixels.
    reading.read_scan(pdf, windows, template_page_sizes={1: (1224.0, 1584.0)}, ocr=fake_ocr)
    width, height = crops[0]
    assert 200 <= width <= 215 and 22 <= height <= 32
    # An OCR failure on one crop is an empty reading, not an error.
    def failing(png: bytes):
        raise reading.TemplateOcrError("engine down")

    results = reading.read_scan(pdf, windows, template_page_sizes={1: (612.0, 792.0)}, ocr=failing)
    assert results[0].text == "" and results[0].confidence == 0.0


def test_read_scan_ignores_windows_on_pages_the_scan_lacks():
    pdf = acroform_pdf()
    windows = [reading.FieldWindow(name="later", label="Later", page=4, rect=(10.0, 10.0, 60.0, 30.0))]
    assert reading.read_scan(pdf, windows, template_page_sizes={}, ocr=lambda png: ("x", 1.0)) == []
    with pytest.raises(reading.TemplateOcrError):
        reading.read_scan(b"not a pdf", windows, template_page_sizes={}, ocr=lambda png: ("x", 1.0))


def test_normalize_scan_rasterises_images_and_passes_pdfs_through():
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (200, 100), "white").save(buffer, format="PNG")
    png = buffer.getvalue()
    assert reading.normalize_scan(png, "scan.png").startswith(b"%PDF")
    pdf = acroform_pdf()
    assert reading.normalize_scan(pdf, "scan.pdf") is pdf


def test_read_scan_keeps_clips_only_for_unreadable_fields_when_asked():
    pdf = acroform_pdf()
    windows = reading.field_windows(_schema_from(pdf))
    names = [window.name for window in windows]

    seen: list = []

    def fake_ocr(png: bytes):
        # The first window reads well; the rest are below the floor.
        seen.append(1)
        return ("Ada", 0.9) if len(seen) == 1 else ("", 0.1)
    readings = reading.read_scan(
        pdf, windows, template_page_sizes=reading.page_sizes(pdf), ocr=fake_ocr,
        keep_clips_below=0.35, max_clips=2,
    )
    assert readings[0].clip_png is None
    kept = [item for item in readings if item.clip_png]
    assert len(kept) == 2 and all(item.clip_png.startswith(b"\x89PNG") for item in kept)
    assert all(item.read_by == "ocr" for item in readings)
    assert "clip_png" not in readings[0].as_dict() and readings[0].as_dict()["read_by"] == "ocr"
    # Without the flag nothing is retained, however low the confidence.
    plain = reading.read_scan(pdf, windows, template_page_sizes=reading.page_sizes(pdf), ocr=lambda png: ("", 0.0))
    assert all(item.clip_png is None for item in plain)
    assert len(names) >= 3
