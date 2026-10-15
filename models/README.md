# FSRCNN x2 快速预训练模型

来源：[Saafke/FSRCNN_Tensorflow](https://github.com/Saafke/FSRCNN_Tensorflow)，T91 训练、General100 微调，导出为 OpenCV 可加载的 TensorFlow 图。

- 固定提交：`6a4812c4ef1c4f5947d79beafa32a05a6eb4a94d`
- 文件：`models/FSRCNN_x2.pb`，38,973 字节，随源码提供
- SHA256：`366b33f0084c7b3f2bf6724f0a2c77bca94fcec9d7b6d72389d330073b380d5c`
- Apache-2.0 许可证见 `LICENSE-FSRCNN.txt`

`python model_assets.py` 校验现有文件，文件缺失或损坏时才下载；使用 HTTPS 证书和 SHA256 双重校验。模型推理在 CPU 进行，原生放大 2 倍，再适配用户选择的输出尺寸。相比 EDSR，FSRCNN 更轻更快，效果不同，不保证几何符号完全准确。

旧版 EDSR 权重不会删除，但当前不再加载或打包；保留原许可证 `LICENSE-EDSR.txt` 供已有 EDSR 副本使用。
