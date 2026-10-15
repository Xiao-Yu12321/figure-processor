# EDSR x2 预训练模型

来源：[Saafke/EDSR_Tensorflow](https://github.com/Saafke/EDSR_Tensorflow)，作者使用 DIV2K 数据集训练并导出为 OpenCV 可加载的 TensorFlow 图。

- 固定提交：`06c7bd65b0305c2955328f8f2721ea86c341f660`
- 文件：`models/EDSR_x2.pb`，38,490,162 字节
- SHA256：`585623221baa070279a0d1e7e113a4c3faba0f318ca7fdd9a65d9afc0763d9b4`
- 原仓库许可证：Apache-2.0，见 `LICENSE-EDSR.txt`

使用 `python model_assets.py` 下载或修复；下载完成及首次加载时均校验 SHA256。下载器使用 HTTPS 证书验证，不自动下载其他权重。此模型执行 2 倍超分辨率，随后按用户选择调整至最终倍数；不是针对几何题训练，可能改变细小标记，需与原图核对。
