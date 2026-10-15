"""Pinned lightweight FSRCNN weights from the model author's repository."""
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'FSRCNN_x2.pb'
MODEL_URL = 'https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/6a4812c4ef1c4f5947d79beafa32a05a6eb4a94d/models/FSRCNN_x2.pb'
MODEL_SHA256 = '366b33f0084c7b3f2bf6724f0a2c77bca94fcec9d7b6d72389d330073b380d5c'


def verified_model():
    return MODEL_PATH.is_file() and hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256


def download_model():
    if verified_model():
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=MODEL_PATH.parent, suffix='.part')
    try:
        digest = hashlib.sha256()
        with os.fdopen(descriptor, 'wb') as output, urllib.request.urlopen(MODEL_URL, timeout=90) as response:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100_000:
                    raise RuntimeError('模型下载大小异常。')
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != MODEL_SHA256:
            raise RuntimeError('模型 SHA256 校验失败，未启用此文件。')
        os.replace(name, MODEL_PATH)
    finally:
        Path(name).unlink(missing_ok=True)
    return MODEL_PATH


if __name__ == '__main__':
    print('Model ready:', download_model())
