import base64
from io import BytesIO
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from processor import ProcessingError, process_image, validate_options, parse_crop, crop_image, MAX_OUTPUT_PIXELS, load_image
from enhancement import EnhancementError, capabilities, enhance
from desktop_automation import DesktopError, desktop_enhance
from experiments.line_cleanup import clean_lines

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
def index():
    return render_template(
        "index.html",
        styles=(STATIC_DIR / "style.css").read_text(encoding="utf-8"),
        scripts=(STATIC_DIR / "crop-selection.js").read_text(encoding="utf-8") + '\n' +
                (STATIC_DIR / "app.js").read_text(encoding="utf-8"),
    )


@app.get("/api/capabilities")
def available_engines():
    return jsonify(capabilities())


@app.post("/api/process")
def process():
    started = perf_counter()
    image = request.files.get("image")
    if image is None or not image.filename:
        return jsonify(error="请先上传或粘贴图片。"), 400
    try:
        engine = request.form.get("engine", "basic")
        if engine not in ("basic", "line", "local", "doubao", "desktop"):
            raise ProcessingError("未知清晰化模式。")
        if engine == 'desktop':
            if request.remote_addr not in ('127.0.0.1', '::1'):
                return jsonify(error='豆包客户端自动化仅允许在本机通过 127.0.0.1 访问。'), 403
            origin = request.headers.get('Origin')
            if origin:
                parsed = urlsplit(origin)
                if (parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or
                        parsed.netloc != request.host or parsed.scheme != request.scheme):
                    return jsonify(error='不能从其他网页触发桌面自动化，请打开本机程序页面。'), 403
        options = dict(
            scale=int(request.form.get("scale", 2)),
            tolerance=int(request.form.get("tolerance", 24)),
            sharpen=int(request.form.get("sharpen", 100)),
            padding=int(request.form.get("padding", 8)),
            denoise=request.form.get("denoise") == "true",
            background=request.form.get("background", "uniform"),
        )
        validate_options(options['scale'], options['tolerance'], options['sharpen'],
                         options['background'], options['padding'])
        data = image.read()
        crop = request.form.get('crop')
        source_size = None
        if crop:
            data, source_size, _ = crop_image(data, parse_crop(crop))
        original = None
        line_stats = None
        if engine == 'line':
            threshold = int(request.form.get('line_threshold', 170))
            smooth = float(request.form.get('line_smooth', .5))
            ink = request.form.get('line_ink', '#000000')
            decoded = load_image(data)
            try:
                result = clean_lines(decoded, threshold=threshold, smooth=smooth, ink=ink)
            except ValueError as exc:
                if 'No foreground retained' in str(exc):
                    raise ProcessingError('没有找到可保留的线条，请调高去灰阈值或检查选区。') from exc
                raise ProcessingError('线稿参数不正确：阈值为 0–254，平滑为 0–2，颜色使用 #RRGGBB。') from exc
            buffer = BytesIO()
            result.smoothed.save(buffer, 'PNG')
            data = buffer.getvalue()
            line_stats = result.stats
            # Already transparent: never threshold or sharpen these edges again.
            options.update(background='keep', sharpen=0, denoise=False)
        elif engine == 'desktop':
            data, original = desktop_enhance(data)
            options['scale'] = 1
        elif engine != "basic":
            data, original = enhance(data, engine, options['scale'])
            options['scale'] = 1
        png, info = process_image(
            data, **options,
        )
        if original:
            info['original'] = original
        info['engine'] = engine
        if line_stats is not None:
            info['line_cleanup'] = line_stats
        if source_size:
            info['source'] = source_size
    except (EnhancementError, DesktopError) as exc:
        return jsonify(error=str(exc)), exc.status
    except ProcessingError as exc:
        return jsonify(error=str(exc)), 400
    except (ValueError, TypeError):
        return jsonify(error="参数格式不正确。"), 400
    encoded = base64.b64encode(png).decode()
    info['processing_ms'] = round((perf_counter() - started) * 1000, 1)
    return jsonify(image="data:image/png;base64," + encoded, **info)


@app.post('/api/crop')
def crop_result():
    image = request.files.get('image')
    if image is None or not image.filename:
        return jsonify(error='请先处理图片。'), 400
    try:
        png, _, size = crop_image(image.read(), parse_crop(request.form.get('crop')),
                                  max_pixels=MAX_OUTPUT_PIXELS)
    except ProcessingError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(image='data:image/png;base64,' + base64.b64encode(png).decode(), output=size)


@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return jsonify(error="文件不能超过 20 MB。"), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
