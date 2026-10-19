import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
import pytest

import app as app_module


def sample():
    image = Image.new('RGB', (120, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 70, 60), fill=(210, 210, 210))
    draw.line((20, 20, 100, 80), fill='black', width=2)
    draw.line((80, 15, 80, 30), fill=(140, 140, 140), width=1)
    return image


def request(image, **options):
    data = BytesIO(); image.save(data, 'PNG'); data.seek(0)
    return app_module.app.test_client().post('/api/process', data={
        'image': (data, 'lines.png'), 'engine': 'line', 'scale': '1', 'padding': '0',
        **options,
    })


def pixels(response):
    return np.asarray(Image.open(BytesIO(base64.b64decode(response.json['image'].split(',')[1]))))


def test_line_web_reuses_experiment_without_ai_or_second_background_pass(monkeypatch):
    def forbidden(*args): pytest.fail('Line cleanup must not invoke AI or desktop automation')
    monkeypatch.setattr(app_module, 'enhance', forbidden)
    monkeypatch.setattr(app_module, 'desktop_enhance', forbidden)
    # Conflicting general controls must not recolor/rethreshold the smoothed mask.
    response = request(sample(), line_ink='#1565c0', background='uniform', sharpen='200', denoise='true')
    assert response.status_code == 200, response.json
    data = pixels(response)
    assert np.all(data[:, :, :3] == [21, 101, 192])
    assert np.any(data[:, :, 3] == 0)
    assert np.any((data[:, :, 3] > 0) & (data[:, :, 3] < 255))
    assert response.json['engine'] == 'line'
    assert response.json['line_cleanup']['threshold'] == 170
    assert response.json['processing_ms'] > 0


def test_line_web_supports_pre_and_post_crop():
    response = request(sample(), crop='[10,10,110,90]', line_smooth='0')
    assert response.status_code == 200, response.json
    assert response.json['source'] == [120, 100]
    assert response.json['original'] == [100, 80]
    png = base64.b64decode(response.json['image'].split(',')[1])
    image = Image.open(BytesIO(png))
    cropped = app_module.app.test_client().post('/api/crop', data={
        'image': (BytesIO(png), 'result.png'), 'crop': f'[0,0,{image.width//2},{image.height//2}]',
    })
    assert cropped.status_code == 200
    assert cropped.json['output'] == [image.width//2, image.height//2]


@pytest.mark.parametrize('options', [dict(line_threshold='255'), dict(line_threshold='bad'),
                                   dict(line_smooth='nan'), dict(line_smooth='-1'), dict(line_ink='invalid')])
def test_invalid_line_parameters(options):
    response = request(sample(), **options)
    assert response.status_code == 400


def test_empty_image_reports_threshold_guidance():
    response = request(Image.new('RGB', (30, 30), 'white'))
    assert response.status_code == 400
    assert '调高去灰阈值' in response.json['error']


def test_threshold_changes_faint_line_retention():
    image = Image.new('RGB', (40, 40), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((10, 10, 30, 10), fill='black')
    draw.line((10, 30, 30, 30), fill=(190, 190, 190))
    low = request(image, line_threshold='170', line_smooth='0')
    high = request(image, line_threshold='200', line_smooth='0')
    assert low.status_code == high.status_code == 200
    assert high.json['line_cleanup']['foreground_pixels_before_smoothing'] > low.json['line_cleanup']['foreground_pixels_before_smoothing']
