"""Pinned public EDSR weights from the model author's repository."""
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'EDSR_x2.pb'
MODEL_URL = 'https://raw.githubusercontent.com/Saafke/EDSR_Tensorflow/06c7bd65b0305c2955328f8f2721ea86c341f660/models/EDSR_x2.pb'
MODEL_SHA256 = '585623221baa070279a0d1e7e113a4c3faba0f318ca7fdd9a65d9afc0763d9b4'


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
                if total > 45_000_000:
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
