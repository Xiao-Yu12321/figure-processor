import base64
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app import app
from processor import ProcessingError, process_image


def encode(image):
    stream = BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def geometry():
    image = Image.new("RGB", (240, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(40, 150), (120, 30), (200, 150)], outline="black", width=2)
    draw.text((116, 15), "A", fill="black")
    draw.text((28, 153), "B", fill="black")
    draw.text((201, 153), "C", fill="black")
    for x in range(50, 191, 12):
        draw.line((x, 135, x + 5, 135), fill=(80, 80, 80), width=1)
    draw.ellipse((115, 85, 121, 91), fill=(20, 80, 200))
    return image


def test_geometry_transparency_crop_lines_and_labels():
    png, info = process_image(encode(geometry()), scale=1, background="uniform", padding=8, sharpen=0)
    image = Image.open(BytesIO(png))
    assert image.mode == "RGBA"
    assert image.width < 240 and image.height < 200
    assert image.getpixel((0, 0))[3] == 0
    assert info["background"] == [255, 255, 255]
    pixels = list(image.getdata())
    assert sum(p[3] == 255 and max(p[:3]) < 100 for p in pixels) > 400
    assert any(p[2] > 150 and p[0] < 50 and p[3] > 200 for p in pixels)
    assert not any(min(p[:3]) > 245 and p[3] > 0 for p in pixels)
    assert image.getchannel("A").getbbox() == (8, 8, image.width - 8, image.height - 8)


def test_edge_mode_keeps_enclosed_fill():
    original = Image.new("RGB", (60, 60), "white")
    ImageDraw.Draw(original).rectangle((10, 10, 49, 49), outline="black", width=2)
    result, _ = process_image(encode(original), scale=1, background="edge", padding=0, sharpen=0)
    image = Image.open(BytesIO(result))
    assert image.getpixel((20, 20)) == (255, 255, 255, 255)
    result, _ = process_image(encode(original), scale=1, background="uniform", padding=0, sharpen=0)
    assert Image.open(BytesIO(result)).getpixel((20, 20))[3] == 0


def test_existing_transparency_and_scale():
    original = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((20, 20, 39, 39), fill=(50, 120, 200, 255))
    png, info = process_image(encode(original), scale=2, padding=8)
    assert info["output"] == [56, 56]
    image = Image.open(BytesIO(png))
    assert image.getpixel((25, 25))[3] == 255
    assert image.getpixel((0, 0))[3] == 0


def test_low_tolerance_preserves_faint_line():
    original = Image.new("RGB", (80, 60), "white")
    ImageDraw.Draw(original).line((20, 30, 60, 30), fill=(235, 235, 235))
    png, _ = process_image(encode(original), scale=1, tolerance=2, background="uniform", sharpen=0)
    image = Image.open(BytesIO(png))
    assert image.getchannel("A").getextrema()[1] > 0
    # Faint gray ink becomes translucent black, not a white halo on dark paper.
    assert all(max(pixel[:3]) < 5 for pixel in image.getdata() if pixel[3])


@pytest.mark.parametrize("data, options", [
    (b"broken", {}), (encode(Image.new("RGB", (20, 20), "white")), {}),
    (encode(geometry()), {"scale": 4}), (encode(geometry()), {"background": "invalid"}),
])
def test_invalid_inputs(data, options):
    with pytest.raises(ProcessingError):
        process_image(data, **options)


def test_api_success_and_errors():
    client = app.test_client()
    assert client.get("/").status_code == 200
    response = client.post("/api/process", data={
        "image": (BytesIO(encode(geometry())), "geometry.png"), "background": "uniform",
    })
    assert response.status_code == 200
    png = base64.b64decode(response.json["image"].split(",", 1)[1])
    assert Image.open(BytesIO(png)).mode == "RGBA"
    assert client.post("/api/process").status_code == 400
    assert client.post("/api/process", data={"image": (BytesIO(b"bad"), "bad.png")}).status_code == 400
    assert client.post("/api/process", data={"image": (BytesIO(encode(geometry())), "a.png"), "scale": "oops"}).status_code == 400
    assert client.post("/api/process", data={"image": (BytesIO(b"x" * (20 * 1024 * 1024)), "big.png")}).status_code == 413
