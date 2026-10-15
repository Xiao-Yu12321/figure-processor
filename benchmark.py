"""Measure complete local-model requests, including crop and PNG/JSON encoding."""
import argparse
from io import BytesIO
import json
from time import perf_counter

from PIL import Image, ImageDraw

from app import app
from enhancement import local_model


def run(repeat=2):
    client = app.test_client()
    results = []
    for width, height, scale in [(440, 334, 2), (1000, 760, 2), (1000, 1000, 3)]:
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)
        draw.polygon([(width//5, height*4//5), (width//2, height//5),
                      (width*4//5, height*4//5)], outline='black', width=2)
        for y in range(20, height-20, 35):
            draw.text((10, y), 'A B C 90 1 2 3', fill=(80, 80, 80))
        stream = BytesIO()
        image.save(stream, 'PNG')
        local_model.cache_clear()
        for index in range(repeat):
            started = perf_counter()
            response = client.post('/api/process', data={
                'image': (BytesIO(stream.getvalue()), 'geometry.png'),
                'engine': 'local', 'scale': str(scale), 'background': 'uniform',
            })
            elapsed = perf_counter() - started
            if response.status_code != 200:
                raise RuntimeError(response.json)
            row = dict(width=width, height=height, scale=scale, run=index+1,
                       seconds=round(elapsed, 3), under_10_seconds=elapsed < 10)
            results.append(row)
            print(json.dumps(row), flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', type=int, default=2)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be positive')
    results = run(args.repeat)
    raise SystemExit(0 if all(row['under_10_seconds'] for row in results) else 1)
