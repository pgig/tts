"""
tts_engine.py - 核心 TTS 引擎封装（pyttsx3，跨平台 + 子进程方案）

支持：Windows (SAPI5) / macOS (nsss) / Linux (espeak)
停止机制：通过子进程 + SIGTERM/kill，真正可中断播放中的音频
"""

import sys
import os
import subprocess
import threading
import tempfile
import weakref
from typing import Optional, Callable

import pyttsx3

# PDF 解析优先尝试 PyMuPDF（更快），回退到 PyPDF2（更轻量）
try:
    import fitz  # PyMuPDF
    _PDF_BACKEND = "pymupdf"
except ImportError:
    try:
        import PyPDF2
        _PDF_BACKEND = "pypdf2"
    except ImportError:
        _PDF_BACKEND = None


# ---------------------------------------------------------------------------
# 子进程 TTS 脚本（内联，写入临时文件执行）
# ---------------------------------------------------------------------------

_TTS_SCRIPT_TEMPLATE = r'''
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import pyttsx3

args = {{
    'text': {text_repr},
    'rate': {rate},
    'volume': {volume},
    'voice_id': {voice_id_repr},
    'output_path': {output_path_repr},
}}

engine = pyttsx3.init()
engine.setProperty('rate', args['rate'])
engine.setProperty('volume', args['volume'])
if args['voice_id']:
    engine.setProperty('voice', args['voice_id'])

if args['output_path']:
    engine.save_to_file(args['text'], args['output_path'])
    engine.runAndWait()
    print('DONE_SAVE')
else:
    engine.say(args['text'])
    engine.runAndWait()
    print('DONE')

engine.stop()
del engine
'''


def _build_tts_script(text, rate, volume, voice_id, output_path):
    """构建子进程 TTS 脚本内容"""
    def _repr(s):
        if s is None:
            return 'None'
        return repr(s)

    script = _TTS_SCRIPT_TEMPLATE.format(
        text_repr=_repr(text),
        rate=rate,
        volume=volume,
        voice_id_repr=_repr(voice_id),
        output_path_repr=_repr(output_path),
    )
    return script


# ---------------------------------------------------------------------------
# 主引擎类
# ---------------------------------------------------------------------------

class TTSEngine:
    """
    线程安全的 TTS 引擎封装。

    停止机制（核心修复）：
    - Windows SAPI5 原生 stop() 只清空队列，无法中断正在播放的音频；
    - 本实现通过子进程运行 TTS，stop() 时 kill 子进程，实现真正的音频中断。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

        # 首次初始化以读取可用声音列表
        engine = pyttsx3.init()
        self._voices = engine.getProperty("voices")
        engine.stop()
        del engine

        # 默认参数
        self.rate: int = 150          # 语速 (词/分钟)
        self.volume: float = 1.0       # 音量 0.0 ~ 1.0
        self.voice_id: Optional[str] = (
            self._voices[0].id if self._voices else None
        )

        # 回调
        self._on_done: Optional[Callable] = None

    # ------------------------------------------------------------------
    # 公开属性
    # ------------------------------------------------------------------

    @property
    def voices(self):
        return self._voices

    @property
    def is_speaking(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None  # None = still running

    def set_done_callback(self, cb: Optional[Callable]):
        """设置播放完成回调（stop 后不会触发）"""
        self._on_done = cb

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    def _spawn_tts(self, text: str, output_path: Optional[str] = None):
        """
        启动子进程执行 TTS。
        返回 (proc, script_path)，调用方负责在子进程结束后清理 script_path。
        """
        script = _build_tts_script(text, self.rate, self.volume, self.voice_id, output_path)

        # 写入临时 .py 文件（Windows 子进程无法通过 stdin 传 UTF-8）
        fd, script_path = tempfile.mkstemp(suffix=".py", prefix="tts_")
        # 立即关闭 fd，文件内容在下面写入
        os.close(fd)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
        return script_path

    def speak(self, text: str, block: bool = False, on_done: Optional[Callable] = None):
        """
        朗读文本。

        :param text:    要朗读的字符串
        :param block:   True = 同步阻塞；False = 后台线程
        :param on_done: 播放完成回调（仅正常结束时调用，stop 不触发）
        """
        if not text.strip():
            return

        self.stop()
        self._on_done = on_done

        def _run():
            script_path = self._spawn_tts(text)
            proc = self._proc          # 固定 proc 引用，避免 stop() 把它设为 None
            rc = None
            err_output = b""
            try:
                stdout, stderr = proc.communicate(timeout=300)
                rc = proc.returncode
                err_output = stderr
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                rc = -9
            finally:
                # 清理脚本文件（在 proc 已结束之后）
                try:
                    os.remove(script_path)
                except OSError:
                    pass
                # 竞态：stop() 可能已把 self._proc 设为 None
                if self._proc is proc:
                    self._proc = None
            if rc == 0:
                if self._on_done:
                    self._on_done()
            elif rc not in (None, -1, -9):
                sys.stderr.write(err_output.decode("utf-8", errors="replace"))

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        """立即停止当前播放（发送 SIGTERM / TASKKILL）"""
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        try:
            if sys.platform == "win32":
                # TASKKILL /IM python.exe /T 连带终止所有子进程
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/F", "/T"],
                    capture_output=True,
                    creationflags=0x08000000,
                )
            else:
                proc.terminate()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 文件处理
    # ------------------------------------------------------------------

    def read_pdf(self, filepath: str, max_pages: int | None = None) -> str:
        """
        从 PDF 文件提取纯文本。

        :param filepath:   PDF 文件路径或 bytes
        :param max_pages:  最多读取的页数（None = 全部）
        :return:           提取的文本内容
        :raises ImportError: 未安装 PDF 解析库时抛出
        """
        if _PDF_BACKEND is None:
            raise ImportError(
                "PDF 解析需要 PyMuPDF 或 PyPDF2，请运行：\n"
                "  pip install pymupdf    # 推荐，速度快\n"
                "  或\n"
                "  pip install PyPDF2"
            )

        if _PDF_BACKEND == "pymupdf":
            if isinstance(filepath, bytes):
                doc = fitz.open(stream=filepath, filetype="pdf")
            else:
                doc = fitz.open(filepath)
            total = len(doc)
            limit = min(max_pages or total, total)
            parts = []
            for i in range(limit):
                parts.append(doc[i].get_text())
            doc.close()
            return "\n".join(parts)
        else:  # PyPDF2
            if isinstance(filepath, bytes):
                import io as _io
                bio = _io.BytesIO(filepath)
                reader = PyPDF2.PdfReader(bio)
            else:
                reader = PyPDF2.PdfReader(filepath)
            limit = min(max_pages or len(reader.pages), len(reader.pages))
            parts = [reader.pages[i].extract_text() for i in range(limit)]
            return "\n".join(parts)

    def speak_file(self, filepath: str, encoding: str = "utf-8", block: bool = True):
        """读取文本文件并朗读（根据扩展名自动区分 PDF / 纯文本）"""
        ext = filepath.lower().rsplit(".", 1)[-1]
        if ext == "pdf":
            text = self.read_pdf(filepath)
        else:
            with open(filepath, "r", encoding=encoding) as f:
                text = f.read()
        self.speak(text, block=block)

    def save_to_file(self, text: str, output_path: str, on_done: Optional[Callable] = None):
        """
        将朗读内容保存为音频文件（不播放）。

        :param text:        要朗读的文本
        :param output_path: 输出路径（Windows SAPI5 → .wav）
        :param on_done:     保存完成回调
        """
        self.stop()
        self._on_done = on_done

        def _run():
            script_path = self._spawn_tts(text, output_path)
            proc = self._proc
            rc = None
            err_output = b""
            try:
                stdout, stderr = proc.communicate(timeout=300)
                rc = proc.returncode
                err_output = stderr
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                rc = -9
            finally:
                try:
                    os.remove(script_path)
                except OSError:
                    pass
                if self._proc is proc:
                    self._proc = None
            if rc == 0:
                if self._on_done:
                    self._on_done()
            elif rc not in (None, -1, -9):
                sys.stderr.write(err_output.decode("utf-8", errors="replace"))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # 平台信息
    # ------------------------------------------------------------------

    @staticmethod
    def pdf_backend_name() -> Optional[str]:
        return _PDF_BACKEND

    @staticmethod
    def platform_info() -> dict:
        platform = sys.platform
        backend = {
            "win32": "SAPI5 (Windows)",
            "darwin": "NSSpeechSynthesizer (macOS)",
        }.get(platform, f"espeak ({platform})")
        return {"platform": platform, "backend": backend}
