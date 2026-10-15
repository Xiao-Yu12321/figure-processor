import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
import pytest

import app as app_module


def encode(image):
    stream = BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def decode(response):
    return Image.open(BytesIO(base64.b64decode(response.json['image'].split(',')[1])))


def test_crop_before_processing_retains_only_selected_figure():
    source = Image.new('RGB', (300, 180), 'white')
    draw = ImageDraw.Draw(source)
    draw.rectangle((20, 50, 100, 140), fill='red')
    draw.rectangle((210, 50, 290, 140), fill='blue')
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(encode(source)), 'figures.png'), 'crop': '[0,0,150,180]',
        'scale': '1', 'padding': '0', 'background': 'keep', 'sharpen': '0',
    })
    assert response.status_code == 200, response.json
    assert response.json['source'] == [300, 180]
    assert response.json['original'] == [150, 180]
    image = decode(response)
    assert image.size == (150, 180)
    assert image.getpixel((50, 80)) == (255, 0, 0, 255)
    assert not any(b > 200 and r < 20 for r, g, b, a in image.getdata())


def test_crop_runs_before_model_and_validates_before_paid_api(monkeypatch):
    def enhance(data, engine, scale):
        image = Image.open(BytesIO(data))
        assert image.size == (20, 30)
        return data, list(image.size)
    monkeypatch.setattr(app_module, 'enhance', enhance)
    source = encode(Image.new('RGB', (100, 100), 'black'))
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(source), 'a.png'), 'engine': 'doubao', 'crop': '[10,20,30,50]', 'background': 'keep',
    })
    assert response.status_code == 200, response.json
    def forbidden(*args): pytest.fail('Invalid region must not invoke paid API')
    monkeypatch.setattr(app_module, 'enhance', forbidden)
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(source), 'a.png'), 'engine': 'doubao', 'crop': '[0,0,101,20]',
    })
    assert response.status_code == 400


def test_crop_result_preserves_exact_rgba_without_model(monkeypatch):
    def forbidden(*args): pytest.fail('Result cropping must not rerun enhancement')
    monkeypatch.setattr(app_module, 'enhance', forbidden)
    pixels = np.random.default_rng(3).integers(0, 256, (40, 50, 4), dtype=np.uint8)
    source = Image.fromarray(pixels)
    response = app_module.app.test_client().post('/api/crop', data={
        'image': (BytesIO(encode(source)), 'result.png'), 'crop': '[5,6,40,30]',
    })
    assert response.status_code == 200, response.json
    assert response.json['output'] == [35, 24]
    assert np.array_equal(np.asarray(decode(response)), pixels[6:30, 5:40])


@pytest.mark.parametrize('box', [None, 'bad', '{}', '[0,0,1]', '[0,0,1.5,3]',
                                '[false,0,1,3]', '[0,0,0,4]', '[-1,0,4,4]',
                                '[0,0,51,4]', '[5,4,2,1]'])
def test_invalid_crop(box):
    data = {'image': (BytesIO(encode(Image.new('RGB', (50, 40)))), 'result.png')}
    if box is not None:
        data['crop'] = box
    response = app_module.app.test_client().post('/api/crop', data=data)
    assert response.status_code == 400


def test_postcrop_accepts_output_larger_than_input_limit():
    # Input images cap at 12M pixels, but generated results allow up to 24M.
    source = Image.new('RGBA', (3600, 3600), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((10, 10, 30, 30), fill=(20, 40, 80, 100))
    response = app_module.app.test_client().post('/api/crop', data={
        'image': (BytesIO(encode(source)), 'large-result.png'), 'crop': '[0,0,40,40]',
    })
    assert response.status_code == 200, response.json
    image = decode(response)
    assert image.getpixel((0, 0)) == (0, 0, 0, 0)
    assert image.getpixel((20, 20)) == (20, 40, 80, 100)
