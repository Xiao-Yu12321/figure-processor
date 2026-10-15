import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
import pytest
import requests

import enhancement
from app import app
from model_assets import verified_model


def sample(size=(60, 50)):
    image = Image.new('RGB', size, 'white')
    ImageDraw.Draw(image).polygon([(10, 40), (30, 6), (50, 40)], outline='black', width=2)
    stream = BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def test_real_pretrained_inference_and_api():
    if not verified_model():
        pytest.skip('Download checksum-verified model using python model_assets.py for real inference.')
    response = app.test_client().post('/api/process', data={
        'image': (BytesIO(sample()), 'triangle.png'), 'engine': 'local',
        'scale': '2', 'background': 'uniform', 'padding': '8',
    })
    assert response.status_code == 200, response.json
    result = Image.open(BytesIO(base64.b64decode(response.json['image'].split(',')[1])))
    assert response.json['original'] == [60, 50]
    assert response.json['engine'] == 'local'
    assert result.getpixel((0, 0))[3] == 0
    assert result.getchannel('A').getextrema()[1] > 240


def test_super_resolution_tile_stitching(monkeypatch):
    # Deterministic fake isolates the overlap/crop math from model inference.
    class NearestModel:
        def upsample(self, source):
            return np.repeat(np.repeat(source, 2, axis=0), 2, axis=1)
    monkeypatch.setattr(enhancement, 'local_model', lambda: NearestModel())
    source = np.random.default_rng(1).integers(0, 256, (530, 579, 3), dtype=np.uint8)
    actual = np.asarray(enhancement.local_upscale(Image.fromarray(source)))
    assert np.array_equal(actual, np.repeat(np.repeat(source, 2, axis=0), 2, axis=1))


def test_capabilities_never_expose_credentials(monkeypatch):
    monkeypatch.setenv('ARK_API_KEY', 'test-secret')
    monkeypatch.setenv('ARK_IMAGE_MODEL', 'example-model')
    response = app.test_client().get('/api/capabilities')
    assert response.json['doubao'] is True
    assert b'test-secret' not in response.data and b'example-model' not in response.data


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv('ARK_API_KEY', raising=False)
    monkeypatch.delenv('ARK_IMAGE_MODEL', raising=False)
    response = app.test_client().post('/api/process', data={
        'image': (BytesIO(sample()), 'a.png'), 'engine': 'doubao',
    })
    assert response.status_code == 503
    assert 'ARK_API_KEY' in response.json['error']


def test_doubao_contract_and_pipeline(monkeypatch):
    monkeypatch.setenv('ARK_API_KEY', 'test-secret')
    monkeypatch.setenv('ARK_IMAGE_MODEL', 'example-model')
    def post(url, **kwargs):
        assert url == enhancement.ARK_URL
        assert kwargs['headers']['Authorization'] == 'Bearer test-secret'
        payload = kwargs['json']
        assert payload['model'] == 'example-model'
        assert payload['image'].startswith('data:image/png;base64,')
        assert payload['response_format'] == 'b64_json'
        assert kwargs['allow_redirects'] is False
        import json
        body = json.dumps({'data': [{'b64_json': base64.b64encode(sample()).decode()}]}).encode()
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def iter_content(self, _): yield body
        return Response()
    monkeypatch.setattr(enhancement.requests, 'post', post)
    response = app.test_client().post('/api/process', data={
        'image': (BytesIO(sample()), 'a.png'), 'engine': 'doubao', 'scale': '2',
    })
    assert response.status_code == 200, response.json
    assert response.json['engine'] == 'doubao'
    png = base64.b64decode(response.json['image'].split(',')[1])
    image = Image.open(BytesIO(png))
    assert image.getpixel((0, 0))[3] == 0
    assert image.getchannel('A').getextrema()[1] > 0


def test_api_timeout(monkeypatch):
    monkeypatch.setenv('ARK_API_KEY', 'test-secret')
    monkeypatch.setenv('ARK_IMAGE_MODEL', 'example-model')
    def timeout(*args, **kwargs): raise requests.Timeout('test-secret')
    monkeypatch.setattr(enhancement.requests, 'post', timeout)
    with pytest.raises(enhancement.EnhancementError) as error:
        enhancement.doubao_upscale(Image.new('RGB', (60, 50)))
    assert error.value.status == 504
    assert 'test-secret' not in str(error.value)


def test_invalid_input_does_not_invoke_paid_api(monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('Paid API must not run on invalid input')
    monkeypatch.setattr(enhancement.requests, 'post', forbidden)
    client = app.test_client()
    for image, extra in [(b'broken', {}), (sample(), {'scale': '9'}), (sample(), {'tolerance': '-1'})]:
        response = client.post('/api/process', data={
            'image': (BytesIO(image), 'a.png'), 'engine': 'doubao', **extra,
        })
        assert response.status_code == 400


def test_transparent_input_alpha_preserved(monkeypatch):
    monkeypatch.setattr(enhancement, 'local_upscale', lambda image: image.resize((80, 80)))
    source = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(source).rectangle((10, 10, 30, 30), fill=(20, 60, 100, 255))
    stream = BytesIO(); source.save(stream, 'PNG')
    result, _ = enhancement.enhance(stream.getvalue(), 'local', 2)
    restored = Image.open(BytesIO(result))
    assert restored.size == (80, 80)
    assert restored.getpixel((0, 0))[3] == 0
    assert restored.getpixel((40, 40))[3] == 255
