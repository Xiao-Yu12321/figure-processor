import base64
from pathlib import Path
from time import perf_counter

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from processor import ProcessingError, process_image, validate_options, parse_crop, crop_image, MAX_OUTPUT_PIXELS
from enhancement import EnhancementError, capabilities, enhance

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
        if engine not in ("basic", "local", "doubao"):
            raise ProcessingError("未知清晰化模式。")
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
        if engine != "basic":
            data, original = enhance(data, engine, options['scale'])
            options['scale'] = 1
        png, info = process_image(
            data, **options,
        )
        if original:
            info['original'] = original
        info['engine'] = engine
        if source_size:
            info['source'] = source_size
    except EnhancementError as exc:
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
