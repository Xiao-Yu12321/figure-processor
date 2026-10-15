"""Build a downloadable, self-contained HTML app from the shared interface."""
from pathlib import Path

root = Path(__file__).resolve().parent
template = (root / 'templates/index.html').read_text(encoding='utf-8')
scripts = (root / 'static/app.js').read_text(encoding='utf-8')
start = scripts.index("if (location.protocol === 'http:'")
end = scripts.index('\n}', start) + 2
scripts = scripts[:start] + scripts[end:]
scripts = scripts.replace('由后端完成放大、锐化、去背景和裁边。', '离线基础版；AI 功能请启动 Python 后端使用。')
old = """    const response = await fetch('/api/process', {method: 'POST', body: data, signal: controller.signal});
    const result = await response.json();"""
assert old in scripts
scripts = scripts.replace(old, "    const result = await processLocalImage(data);")
scripts = scripts.replace("    if (!response.ok) throw new Error(result.error || '处理失败，请重试。');\n", '')
old_crop = """    const response = await fetch('/api/crop', {method: 'POST', body: data, signal: controller.signal});
    const result = await response.json();"""
assert old_crop in scripts
scripts = scripts.replace(old_crop, '    const result = await cropLocalImage(blob, box);')
scripts = scripts.replace("    if (!response.ok) throw new Error(result.error || '裁剪失败，请重试。');\n", '')
local = (root / 'static/local-processor.js').read_text(encoding='utf-8')
selection = (root / 'static/crop-selection.js').read_text(encoding='utf-8')
html = template.replace('{{ styles | safe }}', (root / 'static/style.css').read_text(encoding='utf-8'))
html = html.replace('{{ scripts | safe }}', local + '\n' + selection + '\n' + scripts)
html = html.replace('<option value="local">本地快速模型 · FSRCNN</option><option value="doubao">豆包 API</option>', '')
html = html.replace('由后端处理图片。', '离线基础版；AI 模型和 API 功能请启动 Python 后端使用。')
destination = root / '几何截图工坊.html'
destination.write_text(html, encoding='utf-8')
print(destination)
