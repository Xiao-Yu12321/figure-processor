"""Package only explicit project files, including verified pretrained weights."""
from pathlib import Path
import zipfile

from model_assets import MODEL_PATH, verified_model

ROOT = Path(__file__).resolve().parent


def build():
    if not verified_model():
        raise RuntimeError('Run python model_assets.py before creating the model-inclusive package.')
    files = [ROOT / name for name in (
        '.gitignore', 'README.md', 'app.py', 'processor.py', 'enhancement.py',
        'model_assets.py', 'build_standalone.py', 'build_package.py', 'benchmark.py', 'desktop_automation.py',
        'requirements.txt', 'requirements-dev.txt', 'requirements-windows.txt', '几何截图工坊.html',
    )]
    for directory in ('static', 'templates', 'tests', 'models'):
        files.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.part')
                     and (p.suffix != '.pb' or p == MODEL_PATH))
    target = ROOT.parent / 'figure-processor-current.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path('figure-processor') / path.relative_to(ROOT))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
    return target


if __name__ == '__main__':
    print(build())
