const $ = (id) => document.getElementById(id);
let selectedFile = null;
let originalURL = null;
let busy = false;
let generation = 0;
let available = null;

function updateEngineInfo() {
  const engine = $('engine').value;
  let message = '由后端完成放大、锐化、去背景和裁边。';
  if (engine === 'local') message = '轻量超分辨率，原图最多 100 万像素；速度优先，目标 10 秒内完成。' + (available && !available.local ? ' 模型尚未安装。' : '');
  if (engine === 'doubao') message = '外部 API 无法保证 10 秒内完成，可能产生费用并改变字母或细线，请核对原图。' + (available && !available.doubao ? ' 后端尚未配置密钥或模型 ID。' : '');
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
function invalidateResult() {
  generation++;
  $('download').removeAttribute('href');
  $('download').classList.add('disabled');
  $('download').setAttribute('aria-disabled', 'true');
  $('result').hidden = true;
  $('result-placeholder').hidden = false;
  $('result-info').textContent = '处理完成后，可切换底色检查线条和透明边缘。';
}
function selectFile(file) {
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) return status('文件不能超过 20 MB。', true);
  if (!/^image\/(png|jpeg|webp|bmp|x-ms-bmp)$/.test(file.type)) return status('请使用 PNG、JPEG、WebP 或 BMP 图片。', true);
  if (originalURL) URL.revokeObjectURL(originalURL);
  selectedFile = file;
  originalURL = URL.createObjectURL(file);
  $('original').src = originalURL;
  $('original').hidden = false;
  $('placeholder').hidden = true;
  $('source-info').textContent = `${file.name || '粘贴的截图'} · ${(file.size / 1024).toFixed(0)} KB`;
  $('source-info').hidden = false;
  $('process').disabled = busy;
  invalidateResult();
  status('截图已就绪，点击“处理图片”。');
}
$('drop').onclick = () => $('file').click();
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
  busy = true;
  $('process').disabled = true;
  $('process').textContent = '正在处理…';
  status('正在提高清晰度、去除背景并裁剪空白…');
  const controller = new AbortController();
  const timeoutMs = $('engine').value === 'doubao' ? 180000 : 10000;
  const startedAt = performance.now();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch('/api/process', {method: 'POST', body: data, signal: controller.signal});
    const result = await response.json();
    if (version !== generation) return;
    if (!response.ok) throw new Error(result.error || '处理失败，请重试。');
    $('result').src = result.image;
    $('result').hidden = false;
    $('result-placeholder').hidden = true;
    $('result-info').textContent = `${result.original.join(' × ')} → ${result.output.join(' × ')} px · PNG · ${((performance.now() - startedAt) / 1000).toFixed(2)} 秒`;
    $('download').href = result.image;
    $('download').download = (file.name || 'screenshot').replace(/\.[^.]+$/, '') + '-clean.png';
    $('download').classList.remove('disabled');
    $('download').setAttribute('aria-disabled', 'false');
    status('处理完成。若细线缺失，请降低去背景容差。');
  } catch (error) {
    if (version === generation) status(error.name === 'AbortError' ? (timeoutMs === 10000 ? '本次处理超过 10 秒，请缩小截图或选择基础增强。' : '豆包 API 超时，请稍后重试。') : error.message, true);
  } finally {
    clearTimeout(timeout);
    busy = false;
    $('process').disabled = !selectedFile;
    $('process').innerHTML = '处理图片 <span>→</span>';
  }
};
