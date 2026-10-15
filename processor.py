"""Screenshot cleanup with a uniform background; no external image service."""
from io import BytesIO
import json
import warnings

import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from scipy import ndimage

MAX_PIXELS = 12_000_000
MAX_OUTPUT_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ProcessingError(ValueError):
    pass


def validate_options(scale, tolerance, sharpen, background, padding):
    if scale not in (1, 2, 3):
        raise ProcessingError("放大倍数必须为 1、2 或 3。")
    if not 0 <= tolerance <= 100 or not 0 <= sharpen <= 200:
        raise ProcessingError("去背景容差或锐化强度超出范围。")
    if background not in ("edge", "uniform", "keep") or not 0 <= padding <= 100:
        raise ProcessingError("背景模式或边距不正确。")


def load_image(data, *, max_pixels=MAX_PIXELS):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore" if max_pixels > MAX_PIXELS else "error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ("PNG", "JPEG", "WEBP", "BMP"):
                    raise ProcessingError("请上传 PNG、JPEG、WebP 或 BMP 图片。")
                if source.width * source.height > max_pixels:
                    raise ProcessingError(f"图片不能超过 {max_pixels // 10000} 万像素。")
                return ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ProcessingError("无法读取图片，文件可能损坏或尺寸过大。") from exc


def parse_crop(value):
    try:
        box = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ProcessingError('选区格式不正确。') from exc
    if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
        raise ProcessingError('选区必须为四个整数坐标。')
    return box


def crop_image(data, box, *, max_pixels=MAX_PIXELS):
    image = load_image(data, max_pixels=max_pixels)
    left, top, right, bottom = box
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ProcessingError('选区超出图片范围或没有面积，请重新框选。')
    original = list(image.size)
    image = image.crop(box)
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue(), original, list(image.size)


def process_image(data, *, scale=2, tolerance=24, sharpen=100,
                  denoise=False, background="uniform", padding=8):
    validate_options(scale, tolerance, sharpen, background, padding)
    image = load_image(data)
    if image.width * image.height * scale * scale > MAX_OUTPUT_PIXELS:
        raise ProcessingError("放大后的图片不能超过 2400 万像素，请降低倍数。")

    original_size = image.size
    rgba = np.asarray(image).copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3].astype(np.float32) / 255
    detected = None
    if background != "keep":
        border_rgb = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]))
        border_alpha = np.concatenate((alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]))
        opaque = border_rgb[border_alpha > .95]
        # Already transparent images need no inferred background removal.
        if len(opaque) > len(border_rgb) * .5:
            color = np.median(opaque, axis=0)
            detected = [int(x) for x in color]
            distance = np.max(np.abs(rgb - color), axis=2)
            candidate = (distance <= tolerance) | (alpha == 0)
            if background == "edge":
                seeds = np.zeros(candidate.shape, dtype=bool)
                seeds[0] = candidate[0]
                seeds[-1] = candidate[-1]
                seeds[:, 0] = candidate[:, 0]
                seeds[:, -1] = candidate[:, -1]
                removed = ndimage.binary_propagation(seeds, mask=candidate)
            else:
                removed = candidate
            alpha[removed] = 0
            rim = ndimage.binary_dilation(removed) & ~removed
            if np.min(color) >= 230:
                # White-paper matting: gray antialiased ink becomes translucent
                # dark ink, so tiny letters do not acquire pale edge halos.
                coverage = np.clip(1 - np.min(rgb / color, axis=2), 0, 1)
                affected = ~removed if background == "uniform" else rim
            else:
                coverage = np.clip((distance - tolerance) / 12, 0, 1)
                affected = rim
            partial = affected & (coverage > 0) & (coverage < 1)
            a = coverage[partial, None]
            rgb[partial] = np.clip((rgb[partial] - color * (1 - a)) / a, 0, 255)
            alpha[affected] *= coverage[affected]
    rgba[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[:, :, 3] = np.rint(alpha * 255).astype(np.uint8)
    image = Image.fromarray(rgba)
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ProcessingError("没有找到可保留的内容，请降低容差或选择保留背景。")
    image = image.crop(bounds)
    color_image = image.convert("RGB")
    alpha_image = image.getchannel("A")
    if denoise:
        color_image = color_image.filter(ImageFilter.MedianFilter(3))
    size = (image.width * scale, image.height * scale)
    color_image.putalpha(alpha_image)
    # Pillow resizes RGBA in premultiplied space to avoid white edge halos.
    resized = color_image.resize(size, Image.Resampling.LANCZOS)
    color_image = resized.convert("RGB")
    alpha_image = resized.getchannel("A")
    if sharpen:
        color_image = color_image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=sharpen, threshold=3))
    color_image.putalpha(alpha_image)
    output = ImageOps.expand(color_image, border=padding, fill=(0, 0, 0, 0))
    buffer = BytesIO()
    output.save(buffer, format="PNG")
    return buffer.getvalue(), {"original": list(original_size), "output": list(output.size),
                              "background": detected}
