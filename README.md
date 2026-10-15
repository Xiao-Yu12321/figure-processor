# 几何截图工坊

截图上传 / 拖入 / 剪贴板粘贴 → 后端清晰化 → 去除纯色背景 → 自动裁边 → 下载透明 PNG。前端只负责文件上传、参数、预览和下载，服务器模式全部计算在 Python 后端完成。

## Mac / Linux 启动后端版

需要 Python 3.12。终端进入解压后的项目目录后执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python model_assets.py
.venv/bin/python app.py
```

在同一台电脑的浏览器访问端口 5000。源码包包含已校验的 EDSR 权重；下载命令在权重有效时直接复用，不重复联网。服务启动后必须通过它提供的页面使用 AI 功能，双击 HTML 只能使用离线基础版。公网部署请使用生产 WSGI 服务并配置访问控制；API 付费能力不应暴露给未授权用户。

## 三种清晰化方式

| 模式 | 实现 | 是否发送图片给第三方 |
| --- | --- | --- |
| 基础增强 | Pillow Lanczos 放大、可选降噪、非锐化掩模 | 否 |
| 本地模型 EDSR | 下载好的 EDSR x2 预训练权重，OpenCV CPU 分块推理 | 否 |
| 豆包 API | 火山方舟 Seedream 图片编辑接口 | 是，发送至火山引擎 |

本地模型原生放大 2 倍，再适配选择的最终尺寸，不会再次叠加所选倍数。所有模式在清晰化后去背景、裁边并生成透明 PNG。AI 模式保留原有透明通道，原图最多 100 万像素。EDSR 使用 CPU，较大截图可能需要几分钟，前端等待最多 10 分钟；取消等待不代表服务器计算停止。本地模型同一时间仅处理一个请求，其他请求收到忙碌提示。

EDSR 和豆包均不保证数学符号绝对准确，应核对字母、虚线和角度标记。尤其豆包是生成式图片编辑，并非严格保真的超分模型。

## 配置豆包 API

在火山方舟控制台开通支持图片编辑的 Seedream 模型，获取 API Key 和实际模型 ID。普通豆包聊天模型 ID 不适用。后端读取：

- `ARK_API_KEY`：密钥，仅在服务器环境中保存；不要放到前端、源码、截图或聊天中。
- `ARK_IMAGE_MODEL`：控制台提供的图片编辑模型 ID 或对应推理接入点 ID。
- 固定 API 地址：`https://ark.cn-beijing.volces.com/api/v3/images/generations`。

本地启动时可先在 Bash 中安全输入密钥（不会显示输入内容）：

```bash
bash
read -s -p 'ARK_API_KEY: ' ARK_API_KEY
export ARK_API_KEY
export ARK_IMAGE_MODEL='替换为控制台的实际图片编辑模型ID'
.venv/bin/python app.py
```

本项目不自动读取 `.env`。云环境中请在环境设置中安全录入密钥，并设置模型 ID。界面只显示是否配置，不返回密钥或模型 ID。调用可能产生费用；仅在用户选择豆包并点击处理时发起，不自动重试或切换到付费 API。未配置、鉴权失败、超时等情况会给出明确错误，不会伪装为基础增强成功。

接口使用参考：[火山引擎官方 SDK 的图片编辑资源](https://github.com/volcengine/volcengine-python-sdk/blob/247c4aaacf0d18da7d13ca27b2d8b3a4030ac24f/volcenginesdkarkruntime/resources/images/images.py)。需要支持 `image`、`response_format=b64_json` 和指定输出尺寸的模型。输出比例与原图显著不符时停止处理；生成内容本身仍需人工核对。

## 图像处理与限制

- 默认去除全部同色背景，包括封闭图形内部同色底。
- 已有透明背景的图片保留透明度；背景颜色从图片边缘估计。
- 虚线或浅色文字消失时降低容差；细线较多时关闭降噪。
- 裁边保留所有非背景内容，包括文字和题干；不会自动选择某个几何图。
- 棋盘格、白底只影响预览，输出 PNG 保留透明通道。
- 不支持复杂照片背景分割。最大上传 20 MB，基础模式原图 1200 万像素，放大后 2400 万像素。
- 图片在内存中处理，不持久保存原图和结果；豆包模式会发送图片给 API 服务商。

## 离线基础版与打包

`几何截图工坊.html` 是独立的浏览器计算版本，不含后端 AI 功能。双击用 Chrome 打开即可，不需要 Python；原图限制为 600 万像素。

```bash
python3 build_standalone.py
python3 build_package.py
```

源码包包含模型权重、原模型许可证、离线基础版、后端、前端与测试；不包含虚拟环境、密钥或缓存。

## 验证

```bash
.venv/bin/python -m pytest -q
```

测试包含真实 EDSR 推理、分块拼接、透明度保留、参数校验、API 缺失配置以及模拟豆包成功/超时。模型未下载时真实推理测试会明确跳过，不能据此声称模型可用。模拟 API 测试不证明真实付费服务可用，真实调用需要配置后另行验证。
