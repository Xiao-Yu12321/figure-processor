from io import BytesIO
import json
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

import app as app_module
import desktop_automation as desktop


def config():
    return {
        'chat_window': {'title': '豆包', 'executable': 'c:/doubao.exe', 'size': [1000, 800]},
        'composer': [.5, .9], 'result_image': [.5, .5], 'copy_action': [.6, .55],
        'generation_wait': 60, 'attachment_wait': 5,
    }


def png(image):
    stream = BytesIO(); image.save(stream, 'PNG'); return stream.getvalue()


def test_config_validation(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    monkeypatch.setattr(desktop, 'CONFIG', path)
    with pytest.raises(desktop.DesktopError): desktop.load_config()
    path.write_text(json.dumps(config()))
    assert desktop.load_config()['generation_wait'] == 60
    invalid = config(); invalid['copy_action'] = [1.5, .5]
    path.write_text(json.dumps(invalid))
    with pytest.raises(desktop.DesktopError): desktop.load_config()


def test_not_available_without_windows(monkeypatch):
    monkeypatch.setenv('DOUBAO_DESKTOP_ENABLED', '1')
    monkeypatch.setattr(desktop.sys, 'platform', 'linux')
    assert desktop.desktop_available() is False
    with pytest.raises(desktop.DesktopError): desktop.WindowsUI()


def test_windows_dib_clipboard_image_decoding():
    image = Image.new('RGB', (20, 30), (10, 80, 150))
    stream = BytesIO(); image.save(stream, 'BMP')
    dib = stream.getvalue()[14:]
    closed = []
    clipboard = SimpleNamespace(
        OpenClipboard=lambda: None, CloseClipboard=lambda: closed.append(True),
        RegisterClipboardFormat=lambda name: 999,
        IsClipboardFormatAvailable=lambda number: number == 8,
        GetClipboardData=lambda number: dib,
    )
    ui = desktop.WindowsUI.__new__(desktop.WindowsUI)
    ui.clipboard = clipboard
    result = ui.clipboard_image()
    assert result.size == (20, 30)
    assert result.getpixel((10, 10)) == (10, 80, 150, 255)
    assert closed == [True]


class FakeUI:
    def __init__(self):
        self.sent = []
        self.clicks = []
        self.clock = 0
        self.sequence = 10
        self.image = Image.new('RGB', (100, 100), 'white')
        ImageDraw.Draw(self.image).line((10, 10, 90, 90), fill='black', width=2)
        self.gui = SimpleNamespace(GetForegroundWindow=lambda: 7)
        self.mouse = SimpleNamespace(press=self.sent.append)
    def checkpoint(self): pass
    def find_window(self, spec): return 7
    def click(self, handle, point, button='left'): self.clicks.append(button)
    def paste_image(self, handle, image): pass
    def paste_text(self, handle, text): pass
    def sleep(self, seconds): self.clock += seconds
    def clipboard_sequence(self): return self.sequence
    def click_copy_menu(self, handle, point): self.sequence += 1
    def clipboard_image(self): return self.image


def test_workflow_single_send_and_context_copy(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    result = desktop.run_workflow(Image.new('RGB', (60, 50), 'white'), config(), ui)
    assert ui.sent == ['enter']
    assert ui.clicks == ['left', 'right']
    assert result.size == (100, 100)


def test_copy_only_does_not_send_any_messages(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    result = desktop.copy_result(config(), ui)
    assert result.size == (100, 100)
    assert ui.clicks == ['right']
    assert ui.sent == []


def test_old_clipboard_is_never_accepted(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    def forbidden(): pytest.fail('Unchanged clipboard must not be read')
    ui.clipboard_image = forbidden
    with pytest.raises(desktop.DesktopError) as error:
        desktop.wait_clipboard_image(ui, 10, timeout=1)
    assert error.value.status == 504


def test_text_clipboard_and_saved_input_are_rejected(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    ui.clipboard_image = lambda: None
    with pytest.raises(desktop.DesktopError): desktop.wait_clipboard_image(ui, 9, timeout=1)
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    with pytest.raises(desktop.DesktopError) as error:
        desktop.run_workflow(ui.image.copy(), config(), ui)
    assert error.value.status == 409


def test_failed_workflow_does_not_resend(monkeypatch):
    ui = FakeUI()
    monkeypatch.setattr(desktop.time, 'monotonic', lambda: ui.clock)
    def fail(*args): raise desktop.DesktopError('Menu unavailable')
    ui.click_copy_menu = fail
    with pytest.raises(desktop.DesktopError):
        desktop.run_workflow(Image.new('RGB', (60, 50)), config(), ui)
    assert ui.sent == ['enter']


def test_desktop_request_keeps_native_output_size_and_crop(monkeypatch):
    def enhance(data):
        source = Image.open(BytesIO(data))
        assert source.size == (20, 30)
        result = Image.new('RGBA', (80, 120), (10, 20, 30, 255))
        return png(result), list(source.size)
    monkeypatch.setattr(app_module, 'desktop_enhance', enhance)
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(png(Image.new('RGB', (100, 100)))), 'a.png'),
        'engine': 'desktop', 'crop': '[10,20,30,50]', 'scale': '3', 'padding': '0', 'background': 'keep',
    }, headers={'Origin': 'http://localhost'})
    assert response.status_code == 200, response.json
    assert response.json['original'] == [20, 30]
    assert response.json['output'] == [80, 120]


@pytest.mark.parametrize('remote, origin', [('10.0.0.5', None), ('127.0.0.1', 'https://other.example')])
def test_other_computers_and_websites_cannot_trigger_desktop(monkeypatch, remote, origin):
    def forbidden(*args): pytest.fail('Untrusted request must not operate desktop')
    monkeypatch.setattr(app_module, 'desktop_enhance', forbidden)
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(png(Image.new('RGB', (10, 10)))), 'a.png'), 'engine': 'desktop',
    }, headers={'Origin': origin} if origin else {}, environ_overrides={'REMOTE_ADDR': remote})
    assert response.status_code == 403


def test_desktop_disabled_has_clear_error_without_api_fallback(monkeypatch):
    monkeypatch.setattr(desktop, 'desktop_available', lambda: False)
    response = app_module.app.test_client().post('/api/process', data={
        'image': (BytesIO(png(Image.new('RGB', (10, 10)))), 'a.png'), 'engine': 'desktop',
    })
    assert response.status_code == 503
    assert 'DOUBAO_DESKTOP_ENABLED' in response.json['error']
