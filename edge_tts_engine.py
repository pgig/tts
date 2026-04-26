"""
edge_tts_engine.py - Edge TTS 引擎（多音色，微软云端合成）

pip install edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple --user

优势：
  - 50+ 音色（中文/英文/方言全覆盖）
  - 音质远优于 pyttsx3（神经网络合成）
  - 跨平台（Windows/macOS/Linux）
  - 支持语速、音调、音量调节

劣势：
  - 需要网络连接
  - 需等待网络合成（1~3秒延迟）
"""

import asyncio
import edge_tts
import io
import json
import os
import pygame
import sys
import threading

# ── 代理配置文件 ────────────────────────────────────────────────────
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_config.json")


def load_proxy_config() -> dict:
    """加载代理配置，默认不走代理。"""
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("proxy", {})
        except Exception:
            pass
    return {}


def save_proxy_config(proxy_cfg: dict):
    """保存代理配置到 JSON 文件。"""
    try:
        cfg = {}
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["proxy"] = proxy_cfg
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write(f"[EdgeTTS] save config error: {e}\n")


pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)


class EdgeTTSEngine:
    """Edge TTS 引擎，支持播放/保存/停止"""

    # 默认音色（中文女声，温暖）
    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

    def __init__(
        self,
        voice: str | None = None,
        rate: int = 0,        # -100 ~ +100，0 为正常
        pitch: int = 0,       # -50 ~ +50 Hz
        volume: float = 1.0,  # 0 ~ 2.0，1.0 为正常
        proxy: str = "",      # 代理地址，空字符串表示不走代理
    ):
        self.voice = voice or self.DEFAULT_VOICE
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.proxy = proxy     # ""=直连(不走系统代理), None=系统代理, "http://..."=手动代理
        self._speaking = False
        self._thread: threading.Thread | None = None
        self._stop_requested = False

    # ------------------------------------------------------------------
    # 静态方法
    # ------------------------------------------------------------------

    @staticmethod
    def list_voices(lang: str = "zh", proxy: str | None = "") -> list[dict]:
        """列出所有可用音色，可选语言过滤（如 "zh"、"en"、"all"）

        proxy: ""=直连(不走系统代理), None=系统代理, "http://..."=手动代理
        """
        try:
            # 在后台线程中调用时，需创建独立的 event loop 避免与主线程冲突
            loop = asyncio.new_event_loop()
            try:
                # proxy="" → 直连(不走系统代理)；proxy=None → 走系统代理
                raw = loop.run_until_complete(
                    edge_tts.list_voices(proxy=proxy)
                )
            finally:
                loop.close()
        except Exception as e:
            sys.stderr.write(f"[EdgeTTS] list_voices error: {type(e).__name__}: {e}\n")
            raw = []
        result = []
        for v in raw:
            short = v.get("ShortName", v.get("Name", ""))
            locale = v.get("Locale", "")
            # lang 为空或 "all" 时不过滤
            if lang and lang != "all" and not locale.startswith(lang):
                continue
            result.append({
                "short_name": short,
                "name": v.get("Name", short),
                "gender": v.get("Gender", "Unknown"),
                "locale": locale,
                "friendly": v.get("FriendlyName", ""),
            })
        return result

    @staticmethod
    def platform_info() -> dict:
        return {
            "backend": "Edge TTS (微软神经网络)",
            "platform": sys.platform,
            "net_required": True,
        }

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        # 轮询 pygame 播放状态，线程 alive 作为辅助
        if pygame.mixer.music.get_busy():
            return True
        return self._speaking

    @property
    def voices(self) -> list:
        """返回 voices 列表（兼容 pyttsx3 接口）"""
        return self.list_voices()

    # ------------------------------------------------------------------
    # 核心功能
    # ------------------------------------------------------------------

    def _rate_str(self) -> str:
        """Edge TTS rate 字符串：+X% / -X%"""
        return f"{self.rate:+d}%"

    def _pitch_str(self) -> str:
        """Edge TTS pitch 字符串：+XHz / -XHz"""
        return f"{self.pitch:+d}Hz"

    def _volume_str(self) -> str:
        """Edge TTS volume 字符串：+X% / -X%"""
        # volume 0~2.0 → +-100%
        v = int(round((self.volume - 1.0) * 100))
        return f"{v:+d}%"

    async def _synthesize(self, text: str, output_path: str | None = None,
                          progress_callback=None) -> bytes:
        """异步合成音频，返回 wav_bytes（在 output_path 为 None 时）"""
        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self._rate_str(),
            pitch=self._pitch_str(),
            volume=self._volume_str(),
            proxy=self.proxy,
        )
        if output_path:
            # 用 stream() 逐块写入，支持进度回调
            chunk_count = 0
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                        chunk_count += 1
                        if progress_callback and chunk_count % 4 == 0:
                            progress_callback(f"合成中… 已接收 {chunk_count} 个数据块")
            if progress_callback:
                progress_callback("合成完成")
            return b""
        # 保存到 BytesIO
        buf = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)

    def speak(self, text: str, block: bool = True, on_done=None):
        """
        合成并播放音频（pygame.mixer 纯内存播放，无临时文件）。

        Args:
            text:    要朗读的文本
            block:   True = 同步等待播放完毕；False = 后台播放
            on_done: 播放完毕后调用的回调函数（可选）
        """
        self._stop_requested = False

        def _worker():
            try:
                loop = asyncio.new_event_loop()
                try:
                    mp3_bytes = loop.run_until_complete(self._synthesize(text))
                finally:
                    loop.close()
                if self._stop_requested or not mp3_bytes:
                    self._speaking = False
                    return

                # pygame 纯内存播放，无需临时文件
                buf = io.BytesIO(mp3_bytes)
                pygame.mixer.music.load(buf)
                pygame.mixer.music.play()

                self._speaking = True

                # 轮询播放状态（block 时等待，非 block 时让 is_speaking 实时更新）
                while pygame.mixer.music.get_busy() and not self._stop_requested:
                    pygame.time.Clock().tick(30)

                pygame.mixer.music.unload()
                self._speaking = False

                if on_done and not self._stop_requested:
                    on_done()
            except Exception as e:
                sys.stderr.write(f"[EdgeTTS] speak error: {type(e).__name__}: {e}\n")
                self._speaking = False
                if on_done and not self._stop_requested:
                    on_done()
                # 传播异常，让 GUI 层可以检测网络错误并降级
                if not self._stop_requested:
                    raise

        if block:
            _worker()
        else:
            t = threading.Thread(target=_worker, daemon=True)
            self._thread = t
            t.start()

    def stop(self):
        """停止当前播放"""
        self._stop_requested = True
        pygame.mixer.music.stop()
        self._speaking = False

    def save_to_file(self, text: str, output_path: str,
                     progress_callback=None):
        """
        将文本合成为音频文件并保存。

        Args:
            text:             要转换的文本
            output_path:      输出文件路径（.mp3 / .wav）
            progress_callback: 进度回调 fn(msg: str)，例如 "合成中… 12%"
        """
        ext = os.path.splitext(output_path)[1].lower()
        if ext == ".mp3":
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._synthesize_to_mp3(text, output_path,
                                                                 progress_callback=progress_callback))
            finally:
                loop.close()
        else:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._synthesize(text, output_path,
                                                          progress_callback=progress_callback))
            finally:
                loop.close()

    async def _synthesize_to_mp3(self, text: str, output_path: str,
                                  progress_callback=None):
        """异步合成 MP3（带进度回调）"""
        communicate = edge_tts.Communicate(
            text,
            self.voice,
            rate=self._rate_str(),
            pitch=self._pitch_str(),
            volume=self._volume_str(),
            proxy=self.proxy,
        )
        chunk_count = 0
        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                    chunk_count += 1
                    if progress_callback and chunk_count % 4 == 0:
                        progress_callback(f"合成中… 已接收 {chunk_count} 个数据块")
        if progress_callback:
            progress_callback("合成完成")

    # ------------------------------------------------------------------
    # PDF 支持（复用 pyttsx3 的逻辑）
    # ------------------------------------------------------------------

    @staticmethod
    def pdf_backend_name() -> str | None:
        """检测 PDF 解析后端"""
        try:
            import fitz
            return "pymupdf"
        except ImportError:
            pass
        try:
            import PyPDF2
            return "PyPDF2"
        except ImportError:
            return None

    @staticmethod
    def _ocr_page(page, ocr_engine) -> str:
        """用 RapidOCR 对单页 PDF 进行 OCR 识别"""
        import numpy as np
        # 渲染为 numpy 数组（RGB）
        pix = page.get_pixmap(dpi=300)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n)
        # 如果是灰度图（n=1），转成三通道
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        elif img.shape[2] == 4:
            img = img[:, :, :3]  # 去掉 alpha
        result, _ = ocr_engine(img)
        return "\n".join(line[1] for line in result) if result else ""

    @staticmethod
    def read_pdf(source, progress_callback=None) -> str:
        """
        从 PDF 提取文字。
        source: 文件路径（str）或 bytes
        progress_callback: 可选回调，参数为 (current_page, total_pages, message)
        对于扫描件 PDF（无可提取文字），自动使用 RapidOCR 识别。
        """
        import fitz

        if isinstance(source, bytes):
            doc = fitz.open(stream=source, filetype="pdf")
        else:
            doc = fitz.open(source)

        total = len(doc)
        pages = []
        is_scanned = True  # 标记是否为扫描件

        # 第一轮：尝试提取内嵌文字
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(text.strip())
                is_scanned = False
            else:
                pages.append("")  # 占位，后面 OCR 填充
            if progress_callback:
                progress_callback(i + 1, total, "正在提取文字…")

        # 第二轮：如果全部页面都没有文字，用 OCR 兜底
        if is_scanned and doc:
            try:
                from rapidocr_onnxruntime import RapidOCR
                ocr_engine = RapidOCR()
                for i, page in enumerate(doc):
                    ocr_text = EdgeTTSEngine._ocr_page(page, ocr_engine)
                    if ocr_text.strip():
                        pages[i] = ocr_text.strip()
                    if progress_callback:
                        progress_callback(i + 1, total, "正在 OCR 识别…")
            except ImportError:
                pass  # 没装 RapidOCR，返回空

        doc.close()
        return "\n".join(p for p in pages if p)
