"""Backend-only pretrained super-resolution and Volcengine image editing."""
import base64
from functools import lru_cache
from io import BytesIO
import math
import os
import threading

import cv2
import numpy as np
import requests
from PIL import Image

from model_assets import MODEL_PATH, verified_model
from processor import ProcessingError, load_image
from desktop_automation import desktop_available

ARK_URL = 'https://ark.cn-beijing.volces.com/api/v3/images/generations'
MODEL_LOCK = threading.Lock()
MAX_AI_PIXELS = 1_000_000
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class EnhancementError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=1)
def local_model():
    if not verified_model():
        raise EnhancementError('本地模型未安装或校验失败，请在后端运行 python model_assets.py。')
    cv2.setNumThreads(2)
    model = cv2.dnn_superres.DnnSuperResImpl_create()
    model.readModel(str(MODEL_PATH))
    model.setModel('fsrcnn', 2)
    return model


def capabilities():
    return {
        'basic': True,
        'local': verified_model(),
        'doubao': bool(os.environ.get('ARK_API_KEY') and os.environ.get('ARK_IMAGE_MODEL')),
        'desktop': desktop_available(),
    }


def local_upscale(image):
    # Serial inference avoids sharing OpenCV's mutable net between requests.
    if not MODEL_LOCK.acquire(blocking=False):
        raise EnhancementError('本地模型正在处理另一张图片，请稍后重试。', 429)
    try:
        model = local_model()
        source = np.asarray(image)[:, :, ::-1].copy()
        h, w = source.shape[:2]
        result = np.empty((h * 2, w * 2, 3), dtype=np.uint8)
        tile, overlap = 256, 12
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                x0, y0 = max(0, x-overlap), max(0, y-overlap)
                x1, y1 = min(w, x+tile+overlap), min(h, y+tile+overlap)
                block = model.upsample(source[y0:y1, x0:x1])
                tw, th = min(tile, w-x), min(tile, h-y)
                result[y*2:(y+th)*2, x*2:(x+tw)*2] = block[(y-y0)*2:(y-y0+th)*2, (x-x0)*2:(x-x0+tw)*2]
        return Image.fromarray(result[:, :, ::-1])
    except cv2.error as exc:
        raise EnhancementError('本地模型推理失败，请检查模型和 OpenCV 安装。', 500) from exc
    finally:
        MODEL_LOCK.release()


def doubao_upscale(image):
    key, model = os.environ.get('ARK_API_KEY'), os.environ.get('ARK_IMAGE_MODEL')
    if not key or not model:
        raise EnhancementError('豆包 API 尚未配置：后端需要 ARK_API_KEY 和 ARK_IMAGE_MODEL。')
    stream = BytesIO()
    image.save(stream, 'PNG')
    # Seedream-compatible image-edit request. Keep the source aspect ratio.
    ratio = math.sqrt(2048 * 2048 / (image.width * image.height))
    width, height = (max(512, round(d * ratio / 8) * 8) for d in image.size)
    if max(width, height) > 4096:
        raise ProcessingError('豆包模式暂不支持过于狭长的截图，请先裁剪题图。')
    payload = {
        'model': model,
        'image': 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode(),
        'prompt': '仅提升输入几何题图的清晰度、分辨率与线条边缘质量。严格保持原图构图、比例、所有字母、数字、符号、虚线、直角标记和线段连接关系。保留白色背景，不添加、不删除、不重画任何数学内容。',
        'size': f'{width}x{height}', 'response_format': 'b64_json', 'watermark': False,
        'sequential_image_generation': 'disabled',
    }
    try:
        with requests.post(ARK_URL, headers={'Authorization': f'Bearer {key}'},
                           json=payload, timeout=(10, 180), stream=True,
                           allow_redirects=False) as response:
            if response.status_code in (401, 403):
                raise EnhancementError('豆包 API 鉴权失败，请检查密钥、模型权限和服务开通状态。')
            if response.status_code == 429:
                raise EnhancementError('豆包 API 配额不足或请求过于频繁，请稍后重试。', 429)
            if not 200 <= response.status_code < 300:
                raise EnhancementError('豆包 API 请求失败，请核对模型 ID 是否支持 Seedream 图片编辑及当前图片尺寸。', 502)
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise EnhancementError('豆包 API 返回内容过大。', 502)
        import json
        encoded = json.loads(body)['data'][0]['b64_json']
        data = base64.b64decode(encoded, validate=True)
        restored = load_image(data)
        if abs((restored.width / restored.height) / (image.width / image.height) - 1) > .04:
            raise EnhancementError('豆包返回图片比例与原图不符，已停止处理，请改用本地模型。', 502)
        return restored.convert('RGB')
    except requests.Timeout as exc:
        raise EnhancementError('豆包 API 请求超时，请稍后重试。', 504) from exc
    except requests.RequestException as exc:
        raise EnhancementError('无法连接豆包 API，请检查后端网络配置。', 502) from exc
    except (KeyError, IndexError, ValueError, TypeError, ProcessingError) as exc:
        raise EnhancementError('豆包 API 未返回可用图片，请检查模型是否支持 b64_json 图片编辑输出。', 502) from exc


def enhance(data, engine, scale):
    original = load_image(data)
    if original.width * original.height > MAX_AI_PIXELS:
        raise ProcessingError('AI 模式原图最多 100 万像素，请先裁剪或缩小截图。')
    if scale not in (1, 2, 3):
        raise ProcessingError('放大倍数必须为 1、2 或 3。')
    # Transparent inputs are composited on white; preserve source alpha later.
    white = Image.new('RGBA', original.size, 'white')
    white.alpha_composite(original)
    rgb = white.convert('RGB')
    if engine == 'local':
        result = local_upscale(rgb)
    elif engine == 'doubao':
        result = doubao_upscale(rgb)
    else:
        raise ProcessingError('未知清晰化模式。')
    size = (original.width * scale, original.height * scale)
    result = result.resize(size, Image.Resampling.LANCZOS)
    result.putalpha(original.getchannel('A').resize(size, Image.Resampling.LANCZOS))
    output = BytesIO()
    result.save(output, 'PNG')
    return output.getvalue(), list(original.size)
