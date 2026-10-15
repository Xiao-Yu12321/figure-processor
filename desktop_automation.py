"""Calibrated Windows Doubao desktop automation; no API or account passwords."""
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time

from PIL import Image

from processor import load_image

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / '.doubao-desktop.json'
LOCK = threading.Lock()
PROMPT = ('将这张几何题图转换为白底清晰线稿，保留坐标系、几何线段、虚线辅助线、'
          '直角标记与全部字母标注。严格保留原图的几何结构、线段连接关系和相对比例，'
          '不要增删任何数学内容，不添加装饰，生成图片。')


class DesktopError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def load_config():
    try:
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        for key in ('chat_window',):
            window = config[key]
            if (not isinstance(window['title'], str) or not window['title'] or
                    not isinstance(window['executable'], str) or not window['executable'] or
                    len(window['size']) != 2 or any(type(n) is not int or n <= 0 for n in window['size'])):
                raise ValueError()
        for key in ('composer', 'result_image', 'copy_action'):
            point = config[key]
            if len(point) != 2 or any(type(n) not in (int, float) or not 0 <= n <= 1 for n in point):
                raise ValueError()
        if not 15 <= config['generation_wait'] <= 240 or not 2 <= config['attachment_wait'] <= 30:
            raise ValueError()
        if not isinstance(config.get('prompt', PROMPT), str) or not 1 <= len(config.get('prompt', PROMPT)) <= 2000:
            raise ValueError()
        return config
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DesktopError('请先在 Windows 本机运行 python desktop_automation.py calibrate，完成豆包窗口校准。') from exc


def desktop_available():
    if sys.platform != 'win32' or os.environ.get('DOUBAO_DESKTOP_ENABLED') != '1':
        return False
    if any(importlib.util.find_spec(name) is None for name in ('pyautogui', 'win32gui', 'win32clipboard')):
        return False
    try:
        load_config()
        return True
    except DesktopError:
        return False


class WindowsUI:
    def __init__(self):
        if sys.platform != 'win32':
            raise DesktopError('豆包客户端自动化只能在已登录桌面的 Windows 电脑上运行。')
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
            import pyautogui
            import win32clipboard
            import win32gui
            import win32process
            self.mouse = pyautogui
            self.clipboard = win32clipboard
            self.gui = win32gui
            self.process = win32process
            self.mouse.FAILSAFE = True
            self.mouse.PAUSE = .15
        except ImportError as exc:
            raise DesktopError('缺少桌面依赖，请先安装 requirements-windows.txt。') from exc

    def checkpoint(self):
        self.mouse.failSafeCheck()

    def sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.checkpoint()
            time.sleep(min(.25, max(0, deadline-time.monotonic())))

    def executable(self, handle):
        import ctypes
        from ctypes import wintypes
        _, pid = self.process.GetWindowThreadProcessId(handle)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        process = kernel.OpenProcess(0x1000, False, pid)
        if not process:
            raise DesktopError('无法读取豆包窗口身份，请以普通用户运行豆包和本程序。')
        try:
            length = wintypes.DWORD(32768)
            name = ctypes.create_unicode_buffer(length.value)
            if not kernel.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(length)):
                raise DesktopError('无法确认当前窗口所属程序。')
            return str(Path(name.value).resolve()).lower()
        finally:
            kernel.CloseHandle(process)

    def window_info(self, handle):
        left, top, right, bottom = self.gui.GetClientRect(handle)
        return {'title': self.gui.GetWindowText(handle), 'executable': self.executable(handle),
                'size': [right-left, bottom-top]}

    def find_window(self, spec):
        matches = []
        def visit(handle, _):
            if not self.gui.IsWindowVisible(handle):
                return
            # Title equality prevents silently selecting a different conversation.
            if self.gui.GetWindowText(handle) != spec['title']:
                return
            try:
                if self.executable(handle) == spec['executable']:
                    matches.append(handle)
            except DesktopError:
                pass
        self.gui.EnumWindows(visit, None)
        if len(matches) != 1:
            raise DesktopError('未找到校准时的唯一豆包窗口。请打开原会话并保持窗口布局，必要时重新校准。')
        handle = matches[0]
        if self.gui.IsIconic(handle):
            raise DesktopError('请先还原豆包窗口，不要最小化。')
        if self.window_info(handle)['size'] != spec['size']:
            raise DesktopError('豆包窗口大小或显示缩放已改变，请恢复原布局或重新校准。')
        return handle

    def foreground(self, handle):
        if self.gui.GetForegroundWindow() == handle:
            return
        try:
            # Normal desktop focus transfer; always verify the resulting focus.
            self.mouse.keyDown('alt')
            try:
                self.gui.SetForegroundWindow(handle)
            finally:
                self.mouse.keyUp('alt')
        except Exception as exc:
            raise DesktopError('无法切到豆包窗口，请手动将豆包置于前台后重试。') from exc
        self.sleep(.3)
        if self.gui.GetForegroundWindow() != handle:
            raise DesktopError('前台窗口不匹配，已停止键盘操作。')

    def click(self, handle, point, button='left'):
        self.foreground(handle)
        _, _, width, height = self.gui.GetClientRect(handle)
        x, y = self.gui.ClientToScreen(handle, (round(width*point[0]), round(height*point[1])))
        self.mouse.click(x, y, button=button)

    def click_copy_menu(self, handle, point):
        # Reactivating the chat here would close its context menu.
        active = self.gui.GetForegroundWindow()
        if active != handle and self.executable(active) != self.executable(handle):
            raise DesktopError('右键菜单焦点已离开豆包，已停止点击。')
        _, _, width, height = self.gui.GetClientRect(handle)
        x, y = self.gui.ClientToScreen(handle, (round(width*point[0]), round(height*point[1])))
        self.mouse.click(x, y)

    def set_clipboard(self, format_id, value):
        for attempt in range(10):
            try:
                self.clipboard.OpenClipboard()
            except Exception:
                if attempt == 9:
                    raise DesktopError('剪贴板被占用，请关闭剪贴板工具后重试。')
                self.sleep(.1)
                continue
            try:
                self.clipboard.EmptyClipboard()
                self.clipboard.SetClipboardData(format_id, value)
                return
            finally:
                self.clipboard.CloseClipboard()

    def paste_text(self, handle, text):
        if self.gui.GetForegroundWindow() != handle:
            raise DesktopError('焦点已离开目标窗口，已停止粘贴。')
        self.set_clipboard(13, text)  # CF_UNICODETEXT
        self.mouse.hotkey('ctrl', 'v')

    def paste_image(self, handle, image):
        if self.gui.GetForegroundWindow() != handle:
            raise DesktopError('焦点已离开豆包，已停止上传。')
        stream = BytesIO()
        image.convert('RGB').save(stream, 'BMP')
        self.set_clipboard(8, stream.getvalue()[14:])  # CF_DIB, excluding BMP header
        self.mouse.hotkey('ctrl', 'v')

    def clipboard_sequence(self):
        return self.clipboard.GetClipboardSequenceNumber()

    def clipboard_image(self):
        self.clipboard.OpenClipboard()
        try:
            formats = (self.clipboard.RegisterClipboardFormat('PNG'), 8, 17)
            for format_id in formats:
                if self.clipboard.IsClipboardFormatAvailable(format_id):
                    data = self.clipboard.GetClipboardData(format_id)
                    if isinstance(data, bytes):
                        if len(data) > 64 * 1024 * 1024:
                            raise DesktopError('复制结果过大，请缩小原图。')
                        # PIL supports both PNG and headerless Windows DIB data.
                        with Image.open(BytesIO(data)) as image:
                            if image.width * image.height > 12_000_000:
                                raise DesktopError('复制结果不能超过 1200 万像素。')
                            return image.convert('RGBA')
            return None
        finally:
            self.clipboard.CloseClipboard()


def wait_clipboard_image(ui, before, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ui.checkpoint()
        if ui.clipboard_sequence() != before:
            try:
                image = ui.clipboard_image()
                if image is not None:
                    return image
            except DesktopError:
                raise
            except Exception:
                pass  # Clipboard may temporarily be locked or partially filled.
        ui.sleep(.25)
    raise DesktopError('未复制到新的图片。请确认校准的是图片右键菜单的“复制图片”，而非复制链接或文字。', 504)


def copy_result(config, ui):
    chat = ui.find_window(config['chat_window'])
    before = ui.clipboard_sequence()
    ui.click(chat, config['result_image'], button='right')
    ui.sleep(.5)
    ui.click_copy_menu(chat, config['copy_action'])
    return wait_clipboard_image(ui, before)


def run_workflow(image, config, ui):
    chat = ui.find_window(config['chat_window'])
    ui.click(chat, config['composer'])
    ui.paste_image(chat, image)
    ui.sleep(config['attachment_wait'])
    ui.paste_text(chat, config.get('prompt', PROMPT))
    if ui.gui.GetForegroundWindow() != chat:
        raise DesktopError('发送前焦点已离开豆包，已停止。')
    # Exactly one send; never automatically retry a potentially submitted request.
    ui.mouse.press('enter')
    ui.sleep(config['generation_wait'])
    result = copy_result(config, ui)
    # Do not accidentally accept a saved copy of the original attachment.
    if result.size == image.size and result.convert('RGB').tobytes() == image.convert('RGB').tobytes():
        raise DesktopError('复制的图片与输入完全相同，可能点中了上传图。请重新校准生成结果位置。', 409)
    return result


def desktop_enhance(data):
    if not desktop_available():
        raise DesktopError('豆包 App 自动化未启用：需要 Windows、桌面依赖、校准配置及 DOUBAO_DESKTOP_ENABLED=1。')
    source = load_image(data)
    white = Image.new('RGBA', source.size, 'white')
    white.alpha_composite(source)
    if not LOCK.acquire(blocking=False):
        raise DesktopError('豆包 App 正在处理另一张图片，请等待完成。', 429)
    try:
        config = load_config()
        ui = WindowsUI()
        previous_window = ui.gui.GetForegroundWindow()
        result = run_workflow(white.convert('RGB'), config, ui)
        output = BytesIO()
        result.save(output, 'PNG')
        # Return focus to the originating browser when Windows allows it.
        if ui.gui.IsWindow(previous_window):
            try:
                ui.foreground(previous_window)
            except Exception:
                pass
        # Keep generated image dimensions; do not stretch geometry to input ratio.
        return output.getvalue(), list(source.size)
    except DesktopError:
        raise
    except Exception as exc:
        if type(exc).__name__ == 'FailSafeException':
            raise DesktopError('已触发鼠标移至屏幕角落的紧急停止。', 409) from exc
        raise DesktopError('桌面自动化中断，请检查豆包窗口和复制流程。不会重复发送图片。', 502) from exc
    finally:
        LOCK.release()


def calibrate():
    ui = WindowsUI()
    print('请保持豆包登录，打开专门用于清晰化的会话，并保留一张已生成的示例图。')
    print('校准和使用时保持相同窗口大小、侧栏布局和显示缩放。不会读取账号密码。')
    config = {}
    def capture(message, reference=None):
        input(message + '\n按 Enter 后有 5 秒切到豆包并将鼠标移至目标位置：')
        ui.sleep(5)
        handle = ui.find_window(reference) if reference else ui.gui.GetForegroundWindow()
        info = ui.window_info(handle)
        if '豆包' not in info['title'] and 'doubao' not in info['executable'].lower():
            raise DesktopError('前台不是可确认的豆包窗口，请重试。')
        x, y = ui.gui.ScreenToClient(handle, ui.mouse.position())
        width, height = info['size']
        if not (0 <= x <= width and 0 <= y <= height):
            raise DesktopError('鼠标不在目标窗口内。')
        return info, [x/width, y/height]
    config['chat_window'], config['composer'] = capture('1/3：鼠标指向底部消息输入框中心，输入框必须为空。')
    info, config['result_image'] = capture('2/3：鼠标指向最新生成图片的缩略图中心，不是你上传的原图。')
    if info != config['chat_window']:
        raise DesktopError('前两步不是同一个聊天窗口或窗口尺寸发生变化。')
    _, config['copy_action'] = capture('3/3：切回豆包，右键最新生成图，将鼠标停在菜单的“复制/复制图片”上，不要点击。', config['chat_window'])
    config['generation_wait'] = int(input('发送后等待生成的秒数，15–240 [60]：').strip() or '60')
    config['attachment_wait'] = 5
    config['prompt'] = PROMPT
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    previous = CONFIG.read_bytes() if CONFIG.exists() else None
    try:
        os.replace(temporary, CONFIG)
        load_config()
    except Exception:
        if previous is None:
            CONFIG.unlink(missing_ok=True)
        else:
            CONFIG.write_bytes(previous)
        raise
    print('已保存本地校准。请关闭右键菜单，回到原会话，将页面滚动到最新消息，保持输入框为空。')
    print('启用：PowerShell 设置 $env:DOUBAO_DESKTOP_ENABLED="1"，再运行 app.py。')
    print('运行时不要操作键鼠；将鼠标移到屏幕角落可紧急停止。首次必须核对结果是否来自本次生成。')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['calibrate', 'check', 'test-copy'])
    args = parser.parse_args()
    try:
        if args.command == 'calibrate':
            calibrate()
        elif args.command == 'test-copy':
            config = load_config()
            ui = WindowsUI()
            result = copy_result(config, ui)
            print(f'已复制图片：{result.width}×{result.height}。未上传或发送消息。')
            print('请切回我们的网页，Ctrl+V 粘贴，确认是刚才那张生成图；确认后再启用自动发送。')
        else:
            config = load_config()
            ui = WindowsUI()
            ui.find_window(config['chat_window'])
            print('校准配置和聊天窗口匹配；未上传、发送或下载任何内容。')
    except (DesktopError, ValueError) as error:
        print('未完成：', error)
        raise SystemExit(1)
