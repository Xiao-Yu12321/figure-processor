const $ = (id) => document.getElementById(id);
let selectedFile = null;
let originalURL = null;
let busy = false;
let generation = 0;
let available = null;
let fullResult = null;
let currentResult = null;

function updateEngineInfo() {
  const engine = $('engine').value;
  let message = '由后端完成放大、锐化、去背景和裁边。';
  if (engine === 'local') message = '轻量超分辨率，原图最多 100 万像素；速度优先，目标 10 秒内完成。' + (available && !available.local ? ' 模型尚未安装。' : '');
  if (engine === 'doubao') message = '外部 API 无法保证 10 秒内完成，可能产生费用并改变字母或细线，请核对原图。' + (available && !available.doubao ? ' 后端尚未配置密钥或模型 ID。' : '');
  if (engine === 'desktop') message = '自动向已登录的 Windows 豆包 App 发送图片，右键复制生成结果。无需 API 密钥；运行时请勿操作键鼠，移到屏幕角落可停止。生成耗时不保证 10 秒，返回图保留原尺寸。' + (available && !available.desktop ? ' 请先完成本地校准并启用桌面模式。' : '');
  $('scale').disabled = engine === 'desktop';
  $('engine-info').textContent = message;
}
if (location.protocol === 'http:' || location.protocol === 'https:') {
  fetch('/api/capabilities').then(response => response.ok ? response.json() : null).then(data => {
    available = data;
    updateEngineInfo();
  }).catch(() => {});
}

function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
const sourceCrop = new RectangleSelection($('source-stage'), $('original'), $('source-selection'), box => {
  invalidateResult();
  $('source-crop-info').textContent = `仅处理选区 ${box[2]-box[0]} × ${box[3]-box[1]} px`;
  refreshCropControls();
  status('已选定处理区域，点击“处理图片”。');
});
const resultCrop = new RectangleSelection($('result-stage'), $('result'), $('result-selection'), box => {
  $('result-crop-info').textContent = `选区 ${box[2]-box[0]} × ${box[3]-box[1]} px`;
  refreshCropControls();
});
function refreshCropControls() {
  $('source-select').disabled = busy || !selectedFile || !$('original').naturalWidth;
  $('source-select').setAttribute('aria-pressed', String(sourceCrop.active));
  $('source-clear').disabled = busy || !sourceCrop.box;
  $('result-select').disabled = busy || !currentResult || !$('result').naturalWidth;
  $('result-select').setAttribute('aria-pressed', String(resultCrop.active));
  $('result-apply').disabled = busy || !currentResult || !resultCrop.box;
  $('result-clear').disabled = busy || !resultCrop.box;
  $('result-reset').disabled = busy || !fullResult || fullResult === currentResult;
}
function setBusy(value) {
  busy = value;
  if (busy) {sourceCrop.setActive(false); resultCrop.setActive(false);}
  $('process').disabled = busy || !selectedFile;
  refreshCropControls();
}
function showResult(result, name) {
  currentResult = result;
  resultCrop.clear();
  $('result-crop-info').textContent = '';
  $('result').src = result.image;
  $('result').hidden = false;
  $('result-stage').hidden = false;
  $('result-placeholder').hidden = true;
  $('result-info').textContent = result.caption;
  $('download').href = result.image;
  $('download').download = name;
  $('download').classList.remove('disabled');
  $('download').setAttribute('aria-disabled', 'false');
  refreshCropControls();
}
$('original').addEventListener('load', refreshCropControls);
$('result').addEventListener('load', refreshCropControls);
$('source-select').onclick = () => {
  sourceCrop.setActive(!sourceCrop.active);
  $('source-crop-info').textContent = sourceCrop.active ? '在图上拖拽框选，可重新框选。' : (sourceCrop.box ? '已保留处理选区。' : '');
  refreshCropControls();
};
$('source-clear').onclick = () => {
  sourceCrop.clear();
  $('source-crop-info').textContent = '';
  invalidateResult();
  status('已取消选区，将处理完整原图。');
};
$('result-select').onclick = () => {
  resultCrop.setActive(!resultCrop.active);
  $('result-crop-info').textContent = resultCrop.active ? '在图上拖拽框选，再点击“保留选区”。' : '';
  refreshCropControls();
};
$('result-clear').onclick = () => {resultCrop.clear(); $('result-crop-info').textContent = ''; refreshCropControls();};
$('result-reset').onclick = () => {
  if (!fullResult || busy) return;
  showResult(fullResult, $('download').download);
  status('已恢复本次处理的完整结果。');
};
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || busy) return;
  if (sourceCrop.active) $('source-clear').onclick();
  if (resultCrop.active) $('result-clear').onclick();
});
function invalidateResult() {
  generation++;
  fullResult = null;
  currentResult = null;
  resultCrop.clear();
  $('result-stage').hidden = true;
  $('result-crop-info').textContent = '';
  $('download').removeAttribute('href');
  $('download').classList.add('disabled');
  $('download').setAttribute('aria-disabled', 'true');
  $('result').hidden = true;
  $('result-placeholder').hidden = false;
  $('result-info').textContent = '处理完成后，可切换底色检查线条和透明边缘。';
  refreshCropControls();
}
function selectFile(file) {
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) return status('文件不能超过 20 MB。', true);
  if (!/^image\/(png|jpeg|webp|bmp|x-ms-bmp)$/.test(file.type)) return status('请使用 PNG、JPEG、WebP 或 BMP 图片。', true);
  if (originalURL) URL.revokeObjectURL(originalURL);
  selectedFile = file;
  sourceCrop.clear();
  $('source-crop-info').textContent = '';
  originalURL = URL.createObjectURL(file);
  $('original').src = originalURL;
  $('original').hidden = false;
  $('source-stage').hidden = false;
  $('placeholder').hidden = true;
  $('source-info').textContent = `${file.name || '粘贴的截图'} · ${(file.size / 1024).toFixed(0)} KB`;
  $('source-info').hidden = false;
  $('process').disabled = busy;
  invalidateResult();
  status('截图已就绪，点击“处理图片”。');
}
$('drop').onclick = () => {if (!sourceCrop.active) $('file').click();};
$('drop').onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); } };
$('file').onchange = (e) => { selectFile(e.target.files[0]); e.target.value = ''; };
document.addEventListener('paste', (e) => {
  const item = Array.from(e.clipboardData.items).find((item) => item.type.startsWith('image/'));
  if (item) { e.preventDefault(); selectFile(item.getAsFile()); }
});
for (const type of ['dragenter', 'dragover']) $('drop').addEventListener(type, (e) => {
  e.preventDefault(); $('drop').classList.add('dragover');
});
for (const type of ['dragleave', 'drop']) $('drop').addEventListener(type, (e) => {
  e.preventDefault(); $('drop').classList.remove('dragover');
  if (type === 'drop') selectFile(e.dataTransfer.files[0]);
});
for (const id of ['engine', 'tolerance', 'sharpen', 'background', 'scale', 'padding', 'denoise']) {
  $(id).addEventListener('input', () => {
    if ($(id + '-value')) $(id + '-value').value = $(id).value;
    if (id === 'engine') updateEngineInfo();
    invalidateResult();
    if (selectedFile) status('参数已更新，请重新处理。');
  });
}
document.querySelectorAll('[data-bg]').forEach((button) => button.onclick = () => {
  $('result-preview').className = 'preview ' + button.dataset.bg;
  document.querySelectorAll('[data-bg]').forEach((other) => other.classList.toggle('active', other === button));
});
$('process').onclick = async () => {
  if (!selectedFile || busy) return;
  invalidateResult();
  const version = generation;
  const file = selectedFile;
  const data = new FormData();
  data.append('image', file, file.name || 'screenshot.png');
  for (const id of ['engine', 'scale', 'tolerance', 'sharpen', 'padding', 'background']) data.append(id, $(id).value);
  data.append('denoise', $('denoise').checked);
  if (sourceCrop.box) data.append('crop', JSON.stringify(sourceCrop.box));
  setBusy(true);
  $('process').textContent = '正在处理…';
  status($('engine').value === 'desktop' ? '正在自动操作豆包 App，请勿操作键鼠；等待生成后会复制图片并去背景…' : '正在提高清晰度、去除背景并裁剪空白…');
  const controller = new AbortController();
  const engine = $('engine').value;
  const timeoutMs = engine === 'desktop' ? 300000 : engine === 'doubao' ? 180000 : 10000;
  const startedAt = performance.now();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch('/api/process', {method: 'POST', body: data, signal: controller.signal});
    const result = await response.json();
    if (version !== generation) return;
    if (!response.ok) throw new Error(result.error || '处理失败，请重试。');
    result.caption = `${result.original.join(' × ')} → ${result.output.join(' × ')} px · PNG · ${((performance.now() - startedAt) / 1000).toFixed(2)} 秒`;
    fullResult = result;
    showResult(result, (file.name || 'screenshot').replace(/\.[^.]+$/, '') + '-clean.png');
    status('处理完成。若细线缺失，请降低去背景容差。');
  } catch (error) {
    if (version === generation) status(error.name === 'AbortError' ? (timeoutMs === 10000 ? '本次处理超过 10 秒，请缩小截图或选择基础增强。' : engine === 'desktop' ? '豆包 App 自动化等待超时，请检查客户端。不要直接重试，以免重复发送。' : '豆包 API 超时，请稍后重试。') : error.message, true);
  } finally {
    clearTimeout(timeout);
    setBusy(false);
    $('process').innerHTML = '处理图片 <span>→</span>';
  }
};
$('result-apply').onclick = async () => {
  if (busy || !currentResult || !resultCrop.box) return;
  const version = generation;
  const data = new FormData();
  const image = currentResult.image;
  const box = [...resultCrop.box];
  setBusy(true);
  status('正在保留选区…');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const blob = await (await fetch(image)).blob();
    data.append('image', blob, 'result.png');
    data.append('crop', JSON.stringify(box));
    const response = await fetch('/api/crop', {method: 'POST', body: data, signal: controller.signal});
    const result = await response.json();
    if (version !== generation) return;
    if (!response.ok) throw new Error(result.error || '裁剪失败，请重试。');
    result.caption = `${result.output.join(' × ')} px · PNG · 已保留选区`;
    showResult(result, $('download').download);
    status('已保留选区，下载按钮将保存裁剪后的 PNG。');
  } catch (error) {
    if (version === generation) status(error.name === 'AbortError' ? '裁剪超时，请稍后重试。' : error.message, true);
  } finally {
    clearTimeout(timeout);
    setBusy(false);
  }
};
