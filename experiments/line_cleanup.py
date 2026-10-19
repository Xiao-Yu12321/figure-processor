"""Small threshold -> transparent background -> alpha smoothing experiment.

Run with existing Pillow + NumPy; no server, AI, or desktop automation needed.
"""
import argparse
from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import warnings

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

MAX_PIXELS = 12_000_000
ROOT = Path(__file__).resolve().parent


@dataclass
class Result:
    separated: Image.Image
    smoothed: Image.Image
    stats: dict


def clean_lines(image, threshold=170, smooth=.5, ink='#000000'):
    """Threshold first, then smooth alpha without fitting or reconnecting lines."""
    if type(threshold) is not int or not 0 <= threshold <= 254:
        raise ValueError('threshold must be an integer between 0 and 254')
    if not np.isfinite(smooth) or not 0 <= smooth <= 2:
        raise ValueError('smooth must be between 0 and 2 pixels')
    color = ImageColor.getrgb(ink)
    if len(color) != 3:
        raise ValueError('ink must be an RGB color, e.g. #000000 or #1565c0')
    if image.width * image.height > MAX_PIXELS:
        raise ValueError('Input must be at most 12 million pixels')
    started = perf_counter()
    rgba = image.convert('RGBA')
    # Pillow's luminance conversion is a compiled per-pixel operation.
    gray = np.asarray(rgba.convert('RGB').convert('L'))
    source_alpha = np.asarray(rgba.getchannel('A'))
    keep = (gray <= threshold) & (source_alpha > 0)
    if not np.any(keep):
        raise ValueError('No foreground retained; raise threshold or check the input')
    alpha = np.where(keep, source_alpha, 0).astype(np.uint8)
    mask = Image.fromarray(alpha)
    separated = Image.new('RGBA', image.size, (*color, 0))
    separated.putalpha(mask)
    separated_at = perf_counter()
    # Blur only alpha, never the photograph's RGB background: no gray-block halos.
    smoothed_mask = mask.filter(ImageFilter.GaussianBlur(smooth)) if smooth else mask.copy()
    if source_alpha.min() < 255:
        smoothed_mask = Image.fromarray(np.minimum(np.asarray(smoothed_mask), source_alpha))
    smoothed = Image.new('RGBA', image.size, (*color, 0))
    smoothed.putalpha(smoothed_mask)
    finished = perf_counter()
    return Result(separated, smoothed, {
        'input_size': list(image.size), 'threshold': threshold, 'smooth_radius_px': smooth,
        'ink': ink, 'foreground_pixels_before_smoothing': int(np.count_nonzero(alpha)),
        'separate_background_ms': round((separated_at-started)*1000, 3),
        'smooth_ms': round((finished-separated_at)*1000, 3),
        'compute_ms': round((finished-started)*1000, 3),
    })


def load_image(path):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.width*image.height > MAX_PIXELS:
                raise ValueError('Input must be at most 12 million pixels')
            if image.format not in ('PNG', 'JPEG', 'WEBP', 'BMP'):
                raise ValueError('Use PNG, JPEG, WebP or BMP screenshots')
            return ImageOps.exif_transpose(image).convert('RGBA')


def font(size):
    for name in ('DejaVuSans.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def demo_image(size=(640, 480)):
    """Synthetic scan: gray blocks, black lines and a gray dashed altitude."""
    width, height = size
    image = Image.new('RGB', size, (246, 246, 246))
    draw = ImageDraw.Draw(image)
    def p(x, y): return (round(x*width/640), round(y*height/480))
    draw.rectangle([p(35, 90), p(225, 205)], fill=(207, 207, 207))
    draw.rectangle([p(395, 245), p(610, 335)], fill=(225, 225, 225))
    draw.rectangle([p(20, 405), p(180, 450)], fill=(195, 195, 195))
    a, b, c = p(320, 75), p(100, 385), p(540, 385)
    line_width = max(1, round(width/360))
    draw.line([a, b, c, a], fill=(18, 18, 18), width=line_width)
    for y in range(88, 385, 19):
        draw.line([p(320, y), p(320, min(y+10, 385))], fill=(108, 108, 108), width=line_width)
    draw.line([p(320, 369), p(336, 369), p(336, 385)], fill=(45, 45, 45), width=line_width)
    for label, xy in [('A', (313, 45)), ('B', (78, 390)), ('C', (545, 390)), ('D', (313, 392))]:
        draw.text(p(*xy), label, fill=(25, 25, 25), font=font(max(12, round(width/27))))
    draw.ellipse([p(317, 72), p(323, 78)], fill='black')
    stream = BytesIO()
    image.save(stream, 'JPEG', quality=70)
    return Image.open(BytesIO(stream.getvalue())).convert('RGBA')


def comparison(source, result):
    panels = [source, result.separated, result.smoothed]
    factor = min(1, 640/source.width, 640/source.height)
    width, height = max(1, round(source.width*factor)), max(1, round(source.height*factor))
    canvas = Image.new('RGB', (width*3, height+48), 'white')
    draw = ImageDraw.Draw(canvas)
    for i, (panel, title) in enumerate(zip(panels, ['Original', 'Background removed', 'Smoothed transparent PNG'])):
        checker = Image.new('RGBA', (width, height), 'white')
        cells = ImageDraw.Draw(checker)
        for y in range(0, height, 16):
            for x in range(0, width, 16):
                if (x//16+y//16) % 2:
                    cells.rectangle((x, y, x+15, y+15), fill=(232, 237, 232))
        checker.alpha_composite(panel.convert('RGBA').resize((width, height), Image.Resampling.LANCZOS))
        canvas.paste(checker.convert('RGB'), (i*width, 48))
        draw.text((i*width+12, 13), title, fill=(35, 60, 55), font=font(17))
    return canvas


def export(source, output_dir, threshold=170, smooth=.5, ink='#000000'):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    names = ['01-input.png', '02-no-background.png', '03-smoothed.png', '04-comparison.png', 'timing.json']
    if any((output_dir/name).exists() for name in names):
        raise ValueError('Output files already exist; choose a new --output-dir to preserve them')
    started = perf_counter()
    result = clean_lines(source, threshold, smooth, ink)
    source.save(output_dir/names[0])
    result.separated.save(output_dir/names[1])
    result.smoothed.save(output_dir/names[2])
    comparison(source, result).save(output_dir/names[3])
    result.stats['compute_and_export_ms'] = round((perf_counter()-started)*1000, 3)
    (output_dir/names[4]).write_text(json.dumps(result.stats, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['demo', 'run'])
    parser.add_argument('input', nargs='?', type=Path)
    parser.add_argument('--threshold', type=int, default=170)
    parser.add_argument('--smooth', type=float, default=.5)
    parser.add_argument('--ink', default='#000000')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'run' and args.input is None:
        parser.error('run requires an input image path')
    output = args.output_dir or ROOT/'output'/uuid4().hex[:8]
    try:
        source = demo_image() if args.command == 'demo' else load_image(args.input)
        result = export(source, output, args.threshold, args.smooth, args.ink)
        print(json.dumps(result.stats, ensure_ascii=False, indent=2))
        print('Output:', output.resolve())
        if args.command == 'demo':
            for size in ((1000, 1000), (2000, 2000)):
                image = demo_image(size)
                timings = [clean_lines(image, args.threshold, args.smooth, args.ink).stats['compute_ms'] for _ in range(3)]
                print(json.dumps({'benchmark_size': list(size), 'compute_ms_three_runs': timings}))
    except (ValueError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
