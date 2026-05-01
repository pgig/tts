"""
tts_gui.py - 文本转语音 GUI（tkinter，三引擎支持：Edge TTS / F5-TTS / pyttsx3）

用法：
    python tts_gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os
import tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))


# -----------------------------------------------------------------------
# 引擎自动选择（优先顺序：Edge TTS > F5-TTS > pyttsx3）
# -----------------------------------------------------------------------
# USE_EDGE_TTS = True   → Edge TTS（默认）
# USE_EDGE_TTS = False, USE_F5_TTS = True → F5-TTS 声音克隆
# USE_EDGE_TTS = False, USE_F5_TTS = False → pyttsx3（离线备用）

USE_EDGE_TTS = True   # 网络合成，多音色
USE_F5_TTS = True     # 本地声音克隆，需提供参考音频

# pyttsx3 备用引擎（延迟初始化，用于断网降级）
_pyttsx3_engine = None
_pyttsx3_tab_created = False


def _get_pyttsx3_engine():
    """延迟初始化并返回 pyttsx3 备用引擎，失败返回 None"""
    global _pyttsx3_engine
    if _pyttsx3_engine is not None:
        return _pyttsx3_engine
    try:
        from tts_engine import TTSEngine
        _pyttsx3_engine = TTSEngine()
        return _pyttsx3_engine
    except Exception:
        return None


def _is_network_error(exc: Exception) -> bool:
    """判断异常是否为网络相关（连接失败、超时、DNS 等）"""
    msg = str(exc).lower()
    keywords = [
        "connectionerror", "connection refused", "connection reset",
        "timeout", "timed out", "eof occurred",
        "cannot connect", "failed to connect",
        "no route to host", "network is unreachable",
        "name or service not known", "nodename nor servname",
        "ssl", "tls", "certificate",
    ]
    for kw in keywords:
        if kw in msg:
            return True
    # 也按异常类型判断
    exc_type = type(exc).__name__.lower()
    if any(t in exc_type for t in [
        "connectionerror", "connectionrefused", "connectionreset",
        "timeouterror", "sockerror",
    ]):
        return True
    return False

# ── Edge TTS ──────────────────────────────────────────────────────────
if USE_EDGE_TTS:
    try:
        from edge_tts_engine import EdgeTTSEngine
        _active_engine_name = "Edge TTS"
        _engine_requires_network = True
    except ImportError:
        USE_EDGE_TTS = False
        USE_F5_TTS = True

# ── F5-TTS ────────────────────────────────────────────────────────────
if USE_F5_TTS or (not USE_EDGE_TTS):
    try:
        from f5_tts_engine import F5TTSEngine
        # 仅在 Edge TTS 不可用时才更新状态栏显示
        if not USE_EDGE_TTS:
            _active_engine_name = "F5-TTS"
            _engine_requires_network = False
    except ImportError:
        USE_F5_TTS = False
        _active_engine_name = "pyttsx3"
        _engine_requires_network = False


# -----------------------------------------------------------------------
# GUI 主程序
# -----------------------------------------------------------------------

class TTSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("文本转语音 TTS Tool")
        self.resizable(True, True)
        self.minsize(680, 600)

        # 菜单栏
        menubar = tk.Menu(self)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="🌐 网络设置…", command=self._show_network_settings)
        menubar.add_cascade(label="设置", menu=settings_menu)
        self.config(menu=menubar)

        # 创建标签页
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Edge TTS 标签页
        if USE_EDGE_TTS:
            self._edge_tab = self._build_edge_tab()
            self.notebook.add(self._edge_tab, text="Edge TTS  云端合成")
            # 读取已保存的代理配置
            from edge_tts_engine import load_proxy_config
            _proxy_cfg = load_proxy_config()
            if _proxy_cfg.get("use_system"):
                _proxy = None     # 系统代理
            else:
                _proxy = _proxy_cfg.get("address", "")  # 手动代理或直连
            self._edge_engine = EdgeTTSEngine(proxy=_proxy)
            self._setup_edge_tab(self._edge_engine)

        # F5-TTS 标签页
        if USE_F5_TTS:
            self._f5_tab = self._build_f5_tab()
            self.notebook.add(self._f5_tab, text="F5-TTS  声音克隆")
            self._f5_engine = None  # 懒加载
            self._setup_f5_tab()

        # pyttsx3 标签页（仅在 Edge TTS 和 F5-TTS 均 import 失败时显示）
        if not USE_EDGE_TTS and not USE_F5_TTS:
            global _pyttsx3_tab_created
            fallback = _get_pyttsx3_engine()
            if fallback is not None:
                _pyttsx3_tab_created = True
                self._pyttsx3_tab = self._build_pyttsx3_tab()
                self.notebook.add(self._pyttsx3_tab, text="pyttsx3  离线合成")
                self._setup_pyttsx3_tab(fallback)

        # 状态栏
        self.status_var = tk.StringVar()
        ttk.Label(
            self, textvariable=self.status_var,
            relief=tk.SUNKEN, anchor=tk.W, padding=(8, 2),
        ).pack(fill=tk.X, side=tk.BOTTOM)
        self._update_status(f"引擎：{_active_engine_name}" +
            ("  |  🌐 需要网络" if _engine_requires_network else "  |  💻 完全本地运行"))

        # 标签页切换时更新状态栏
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ==================================================================
    # Edge TTS 标签页
    # ==================================================================

    def _build_edge_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        return frame

    def _setup_edge_tab(self, engine):
        f = self._edge_tab
        f.columnconfigure(0, weight=1)

        # 信息栏
        info = ttk.Frame(f)
        info.grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        ttk.Label(info, text=f"引擎：Edge TTS（微软神经网络合成）", foreground="gray").pack(side=tk.LEFT)
        ttk.Label(info, text="🌐 需要网络连接", foreground="gray30").pack(side=tk.RIGHT)

        # 文本输入
        ttk.Label(f, text="输入文本").grid(row=1, column=0, sticky=tk.W)
        text_frame = ttk.Frame(f)
        text_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=4)
        self._edge_text = tk.Text(text_frame, wrap=tk.WORD, font=("微软雅黑", 11), height=8)
        scrollbar = ttk.Scrollbar(text_frame, command=self._edge_text.yview)
        self._edge_text.configure(yscrollcommand=scrollbar.set)
        self._edge_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 工具栏
        toolbar = ttk.Frame(f)
        toolbar.grid(row=3, column=0, sticky=tk.W, pady=(0, 6))
        self._edge_import_btn = ttk.Button(toolbar, text="📂 导入文件", command=self._edge_import)
        self._edge_import_btn.pack(side=tk.LEFT)
        ttk.Button(toolbar, text="🗑 清空", command=lambda: self._edge_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=6)

        # 音色选择
        ttk.Label(f, text="音色").grid(row=4, column=0, sticky=tk.W, pady=(4, 0))
        lang_frame = ttk.Frame(f)
        lang_frame.grid(row=5, column=0, sticky=tk.W, pady=2)
        self._edge_lang = tk.StringVar(value="zh-CN")
        for lang, label in [("zh-CN", "中文"), ("zh-HK", "粤语"), ("zh-TW", "台湾"), ("en-US", "英文")]:
            ttk.Radiobutton(lang_frame, text=label, variable=self._edge_lang,
                            value=lang, command=self._edge_populate_voices).pack(side=tk.LEFT, padx=(0, 6))

        self._edge_voices = []
        self._edge_voice_combo = ttk.Combobox(f, state="readonly", width=50)
        self._edge_voice_combo.grid(row=6, column=0, sticky=tk.EW, pady=(2, 6))
        self._edge_voice_combo.bind("<<ComboboxSelected>>", self._edge_on_voice)
        self._edge_populate_voices()

        # 参数控制
        ctrl = ttk.Frame(f)
        ctrl.grid(row=7, column=0, sticky=tk.EW, pady=(0, 6))
        ctrl.columnconfigure(1, weight=1)
        ctrl.columnconfigure(3, weight=1)

        ttk.Label(ctrl, text="语速：").grid(row=0, column=0, sticky=tk.W)
        self._edge_rate_var = tk.IntVar(value=0)
        ttk.Scale(ctrl, from_=-100, to=100, variable=self._edge_rate_var,
                  orient=tk.HORIZONTAL, command=self._edge_on_rate).grid(row=0, column=1, sticky=tk.EW, padx=4)
        self._edge_rate_lbl = ttk.Label(ctrl, text="0")
        self._edge_rate_lbl.grid(row=0, column=2, padx=(4, 16))

        ttk.Label(ctrl, text="音调：").grid(row=0, column=3, sticky=tk.W)
        self._edge_pitch_var = tk.IntVar(value=0)
        ttk.Scale(ctrl, from_=-50, to=50, variable=self._edge_pitch_var,
                  orient=tk.HORIZONTAL, command=self._edge_on_pitch).grid(row=0, column=4, sticky=tk.EW, padx=4)
        self._edge_pitch_lbl = ttk.Label(ctrl, text="0")
        self._edge_pitch_lbl.grid(row=0, column=5, padx=(4, 0))

        # 按钮
        btns = ttk.Frame(f)
        btns.grid(row=8, column=0, sticky=tk.W, pady=(0, 4))
        self._edge_play = ttk.Button(btns, text="▶ 播放", command=self._edge_play, width=12)
        self._edge_play.pack(side=tk.LEFT)
        self._edge_stop = ttk.Button(btns, text="⏹ 停止", command=self._edge_stop, width=12, state=tk.DISABLED)
        self._edge_stop.pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="💾 保存音频", command=self._edge_save).pack(side=tk.LEFT)

    def _edge_populate_voices(self):
        """后台线程加载音色列表，避免阻塞主线程导致 Combobox 无法使用"""
        lang = self._edge_lang.get()
        self._edge_voice_combo["values"] = ["加载中…"]
        self._edge_voice_combo.set("加载中…")
        self._edge_voice_combo.config(state="disabled")

        def _load():
            voices = self._edge_engine.list_voices(lang=lang, proxy=self._edge_engine.proxy)
            self.after(0, lambda: self._edge_apply_voices(voices, lang))

        threading.Thread(target=_load, daemon=True).start()

    def _edge_apply_voices(self, voices, lang):
        """主线程：将加载好的音色填入 Combobox"""
        # 若用户切换了语言，lang 不再匹配则丢弃本次结果
        # 注意：初始加载时 StringVar 可能未完全初始化，允许空值通过
        current = self._edge_lang.get()
        if current and lang != current:
            return
        self._edge_voices = voices

        # 网络异常导致音色列表为空 → 自动降级到 pyttsx3
        if not voices:
            self._edge_voice_combo.set("（无法加载音色，可能网络异常）")
            self._update_status("⚠️ Edge TTS 无法连接服务器，请检查网络")
            return

        display = [f"{v['short_name']} ({v.get('gender','?')})" for v in voices]
        self._edge_voice_combo["values"] = display
        self._edge_voice_combo.config(state="readonly")
        if display:
            self._edge_voice_combo.current(0)
            self._edge_engine.voice = voices[0]["short_name"]
        else:
            self._edge_voice_combo.set("（无可用音色）")

    def _edge_on_voice(self, _=None):
        idx = self._edge_voice_combo.current()
        if 0 <= idx < len(self._edge_voices):
            self._edge_engine.voice = self._edge_voices[idx]["short_name"]

    def _edge_on_rate(self, val):
        r = int(float(val))
        self._edge_engine.rate = r
        self._edge_rate_lbl.config(text=str(r))

    def _edge_on_pitch(self, val):
        p = int(float(val))
        self._edge_engine.pitch = p
        self._edge_pitch_lbl.config(text=str(p))

    def _edge_play(self):
        text = self._edge_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入文本")
            return
        self._edge_set_speaking(True)
        self._update_status("Edge TTS 正在合成…")

        def _run():
            try:
                self._edge_engine.speak(text, block=True)
                self.after(100, lambda: self._edge_set_speaking(False))
                self.after(100, lambda: self._update_status("就绪"))
            except Exception as e:
                err_msg = str(e)
                is_net = _is_network_error(e)
                self.after(100, lambda: self._edge_set_speaking(False))
                if is_net:
                    self.after(100, lambda m=err_msg: self._edge_network_fallback(text, m))
                else:
                    self.after(100, lambda m=err_msg: self._update_status(f"❌ 错误：{m}"))

        threading.Thread(target=_run, daemon=True).start()

    def _edge_stop(self):
        self._edge_engine.stop()
        self._edge_set_speaking(False)
        self._update_status("已停止")

    def _edge_network_fallback(self, text: str, error_detail: str = ""):
        """Edge TTS 网络失败时，降级到 pyttsx3 离线合成"""
        global _pyttsx3_tab_created
        fallback_engine = _get_pyttsx3_engine()
        if fallback_engine is None:
            self._update_status("❌ Edge TTS 连接失败，且 pyttsx3 未安装")
            messagebox.showerror(
                "网络错误",
                f"Edge TTS 连接失败：{error_detail}\n\n"
                "pyttsx3 离线引擎也未安装，请检查网络或安装 pyttsx3：\n"
                "pip install pyttsx3"
            )
            return

        # 如果 pyttsx3 标签页还没创建，现在创建
        if not _pyttsx3_tab_created:
            _pyttsx3_tab_created = True
            self._pyttsx3_tab = self._build_pyttsx3_tab()
            self.notebook.add(self._pyttsx3_tab, text="pyttsx3  离线合成")
            self._setup_pyttsx3_tab(fallback_engine)

        # 将文本复制到 pyttsx3 标签页
        self._p3_text.delete("1.0", tk.END)
        self._p3_text.insert("1.0", text)

        # 切换到 pyttsx3 标签页
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == "pyttsx3  离线合成":
                self.notebook.select(i)
                break

        self._update_status("⚠️ Edge TTS 连接失败，已切换到 pyttsx3 离线合成")
        messagebox.showinfo(
            "已切换到离线模式",
            "Edge TTS 需要网络连接，当前无法连接服务器。\n\n"
            "已自动切换到 pyttsx3 离线合成引擎。\n"
            "（音色和音质可能与 Edge TTS 不同）"
        )

    def _edge_set_speaking(self, s):
        self._edge_play.config(state=tk.DISABLED if s else tk.NORMAL)
        self._edge_stop.config(state=tk.NORMAL if s else tk.DISABLED)

    def _edge_import(self):
        path = filedialog.askopenfilename(title="导入文件",
            filetypes=[("PDF 文件", "*.pdf"), ("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        ext = path.lower().rsplit(".", 1)[-1]

        # TXT 直接在主线程处理（瞬间完成）
        if ext != "pdf":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if not content.strip():
                    messagebox.showwarning("提示", "该文件内容为空")
                    return
                self._edge_text.delete("1.0", tk.END)
                self._edge_text.insert("1.0", content)
                self._update_status(f"已导入：{os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("读取失败", str(e))
            return

        # PDF：后台线程处理，支持 OCR 进度
        self._edge_import_btn.configure(state=tk.DISABLED)
        self._edge_text.delete("1.0", tk.END)
        self._edge_text.insert("1.0", "正在导入，请稍候…")
        self._edge_text.configure(state=tk.DISABLED)
        self._update_status("正在读取 PDF…")
        basename = os.path.basename(path)

        def _on_progress(current, total, msg):
            self.after(0, lambda: self._update_status(f"{msg}（{current}/{total} 页）"))

        def _run():
            try:
                content = self._edge_engine.read_pdf(path, progress_callback=_on_progress)
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                def _done():
                    self._edge_text.configure(state=tk.NORMAL)
                    self._edge_text.delete("1.0", tk.END)
                    self._edge_import_btn.configure(state=tk.NORMAL)
                    if not content.strip():
                        messagebox.showwarning("提示",
                            "该文件未能提取到文字内容（可能是纯扫描件且未安装 OCR 引擎）")
                        self._update_status("导入失败：未能提取文字")
                    else:
                        self._edge_text.insert("1.0", content)
                        self._update_status(f"已导入：{basename}")
                self.after(0, _done)
            except Exception as e:
                def _err():
                    self._edge_text.configure(state=tk.NORMAL)
                    self._edge_text.delete("1.0", tk.END)
                    self._edge_import_btn.configure(state=tk.NORMAL)
                    messagebox.showerror("读取失败", str(e))
                    self._update_status("导入失败")
                self.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    def _edge_save(self):
        text = self._edge_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入文本")
            return
        path = filedialog.asksaveasfilename(title="保存音频", defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3"), ("WAV", "*.wav"), ("所有文件", "*.*")])
        if not path:
            return
        # 禁用保存按钮防止重复点击
        self._edge_save_btn = self.winfo_children()[0]
        self._update_status("正在合成…")
        text_len = len(text)

        def _on_progress(msg):
            self.after(0, lambda: self._update_status(msg))

        def _run():
            try:
                self._edge_engine.save_to_file(text, path, progress_callback=_on_progress)
                self.after(0, lambda: self._update_status(
                    f"已保存：{os.path.basename(path)} ({text_len} 字)"))
                self.after(0, lambda: messagebox.showinfo("成功", f"已保存到：\n{path}"))
            except Exception as e:
                err_msg = str(e)
                if _is_network_error(e):
                    self.after(0, lambda m=err_msg: self._edge_network_fallback(text, f"保存失败，{m}"))
                else:
                    self.after(0, lambda m=err_msg: messagebox.showerror("失败", m))
                    self.after(0, lambda: self._update_status("保存失败"))

        threading.Thread(target=_run, daemon=True).start()

    # ==================================================================
    # F5-TTS 标签页
    # ==================================================================

    def _build_f5_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        frame.columnconfigure(0, weight=1)
        return frame

    def _setup_f5_tab(self):
        f = self._f5_tab

        # 信息栏
        info = ttk.Frame(f)
        info.grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        ttk.Label(info, text="引擎：F5-TTS（零样本声音克隆，本地推理）", foreground="gray").pack(side=tk.LEFT)
        ttk.Label(info, text="💻 完全本地运行", foreground="gray30").pack(side=tk.RIGHT)

        # ── 参考音频区块 ────────────────────────────────────────────────
        ref_box = ttk.LabelFrame(f, text="参考音频（用于克隆声音）", padding=8)
        ref_box.grid(row=1, column=0, sticky=tk.EW, pady=(0, 6))

        # 录音区（优先于浏览）
        rec_frame = ttk.Frame(ref_box)
        rec_frame.pack(fill=tk.X, pady=(0, 4))

        # 录音提示语：显示要让用户朗读的文本
        rec_prompt_lbl = ttk.Label(rec_frame, text="📋 朗读下方文本录制参考音频：",
                                   font=("微软雅黑", 9, "bold"), foreground="#1a6")
        rec_prompt_lbl.pack(anchor=tk.W)

        # 参考文本：录完之前用于提示用户要说什么，录完后填入实际文本
        _default_text = "今天天气真好，我们去公园散步吧。这是一个用于测试语音克隆的示例文本，大约十五秒长，语速适中即可。"
        self._f5_ref_text = tk.Text(rec_frame, wrap=tk.WORD, font=("微软雅黑", 10), height=3)
        self._f5_ref_text.pack(fill=tk.X, pady=3)
        self._f5_ref_text.insert("1.0", _default_text)
        self._f5_ref_text.tag_configure("hint", foreground="gray50")
        self._f5_ref_text.tag_add("hint", "1.0", "end")

        # 录音控制行
        rec_ctrl = ttk.Frame(rec_frame)
        rec_ctrl.pack(fill=tk.X, pady=2)

        self._f5_recording = False
        self._f5_recording_frames = []   # 录音数据
        self._f5_recording_stream = None

        self._f5_record_btn = ttk.Button(rec_ctrl, text="🎤 开始录音",
                                          command=self._f5_toggle_record, width=16)
        self._f5_record_btn.pack(side=tk.LEFT)

        # 波形/音量指示（Canvas，录音时动态显示）
        self._f5_wave_canvas = tk.Canvas(rec_ctrl, width=120, height=24,
                                          bg="#f0f0f0", highlightthickness=0)
        self._f5_wave_canvas.pack(side=tk.LEFT, padx=6)
        self._f5_wave_bars = []  # 存储音量条矩形 ID

        self._f5_rec_status = ttk.Label(rec_ctrl, text="", foreground="gray",
                                         font=("微软雅黑", 9))
        self._f5_rec_status.pack(side=tk.LEFT, padx=4)

        # 分隔
        ttk.Label(ref_box, text="── 或者选择已有音频文件 ──",
                  foreground="gray50").pack(pady=(2, 2))

        # 浏览区
        ref_top = ttk.Frame(ref_box)
        ref_top.pack(fill=tk.X)
        ttk.Label(ref_top, text="音频文件：").pack(side=tk.LEFT)
        self._f5_ref_path = tk.StringVar()
        ttk.Entry(ref_top, textvariable=self._f5_ref_path, width=50).pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        ttk.Button(ref_top, text="浏览…", command=self._f5_browse_ref).pack(side=tk.LEFT)

        ttk.Label(ref_box, text="提示：参考音频 10~30 秒即可，音质清晰、背景安静效果最佳",
                  foreground="gray").pack(anchor=tk.W, pady=(4, 0))

        # 目标文本
        ttk.Label(f, text="目标文本（要合成的文字）").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        text_frame = ttk.Frame(f)
        text_frame.grid(row=3, column=0, sticky=tk.NSEW, pady=4)
        self._f5_text = tk.Text(text_frame, wrap=tk.WORD, font=("微软雅黑", 11), height=7)
        scrollbar = ttk.Scrollbar(text_frame, command=self._f5_text.yview)
        self._f5_text.configure(yscrollcommand=scrollbar.set)
        self._f5_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 参数
        ctrl = ttk.Frame(f)
        ctrl.grid(row=4, column=0, sticky=tk.EW, pady=(0, 6))
        ctrl.columnconfigure(1, weight=1)

        ttk.Label(ctrl, text="语速：").grid(row=0, column=0, sticky=tk.W)
        self._f5_speed_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl, from_=0.5, to=2.0, variable=self._f5_speed_var,
                  orient=tk.HORIZONTAL).grid(row=0, column=1, sticky=tk.EW, padx=4)
        self._f5_speed_lbl = ttk.Label(ctrl, text="1.0x")
        self._f5_speed_lbl.grid(row=0, column=2, padx=(4, 16))

        ttk.Label(ctrl, text="推理步数：").grid(row=0, column=3, sticky=tk.W)
        self._f5_nfe_var = tk.IntVar(value=32)
        ttk.Scale(ctrl, from_=16, to=64, variable=self._f5_nfe_var,
                  orient=tk.HORIZONTAL).grid(row=0, column=4, sticky=tk.EW, padx=4)
        self._f5_nfe_lbl = ttk.Label(ctrl, text="32")
        self._f5_nfe_lbl.grid(row=0, column=5, padx=(4, 0))

        # 绑定参数回调
        self._f5_speed_var.trace_add("write", lambda *_: self._f5_speed_lbl.config(text=f"{self._f5_speed_var.get():.1f}x"))
        self._f5_nfe_var.trace_add("write", lambda *_: self._f5_nfe_lbl.config(text=str(self._f5_nfe_var.get())))

        # ── 情感控制区块 ─────────────────────────────────────────────
        emo_box = ttk.LabelFrame(f, text="情感风格（可选）", padding=8)
        emo_box.grid(row=5, column=0, sticky=tk.EW, pady=(0, 6))
        emo_box.columnconfigure(1, weight=0)
        emo_box.columnconfigure(3, weight=1)

        # 情感下拉
        ttk.Label(emo_box, text="情感预设：").grid(row=0, column=0, sticky=tk.W)
        from f5_tts_engine import EMOTION_PRESETS
        self._f5_emotion_var = tk.StringVar(value="无（正常）")
        self._f5_emotion_combo = ttk.Combobox(
            emo_box,
            textvariable=self._f5_emotion_var,
            values=list(EMOTION_PRESETS.keys()),
            state="readonly",
            width=16,
        )
        self._f5_emotion_combo.grid(row=0, column=1, sticky=tk.W, padx=(4, 16))

        # CFG 强度（情感引导强度）
        ttk.Label(emo_box, text="情感强度：").grid(row=0, column=2, sticky=tk.W)
        self._f5_cfg_var = tk.DoubleVar(value=2.0)
        ttk.Scale(emo_box, from_=1.0, to=6.0, variable=self._f5_cfg_var,
                  orient=tk.HORIZONTAL, length=140).grid(row=0, column=3, sticky=tk.EW, padx=4)
        self._f5_cfg_lbl = ttk.Label(emo_box, text="2.0")
        self._f5_cfg_lbl.grid(row=0, column=4, padx=(4, 0))
        self._f5_cfg_var.trace_add("write", lambda *_: self._f5_cfg_lbl.config(
            text=f"{self._f5_cfg_var.get():.1f}"))

        # 情感参考音频（可选）— 预置下拉 + 自定义浏览
        ttk.Label(emo_box, text="情感参考音频（可选）：",
                  foreground="gray40").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))

        emo_ref_row = ttk.Frame(emo_box)
        emo_ref_row.grid(row=1, column=1, columnspan=4, sticky=tk.EW, pady=(6, 0))

        # 预置下拉（第一列：固定宽度）
        self._f5_emo_preset_var = tk.StringVar(value="— 不使用 —")
        self._f5_emo_preset_combo = ttk.Combobox(
            emo_ref_row,
            textvariable=self._f5_emo_preset_var,
            state="readonly",
            width=30,
        )
        self._f5_emo_preset_combo.pack(side=tk.LEFT, padx=(0, 4))

        # 自定义浏览按钮
        ttk.Button(emo_ref_row, text="自定义…",
                   command=self._f5_browse_emo_ref).pack(side=tk.LEFT)
        # 刷新预置列表
        ttk.Button(emo_ref_row, text="🔄",
                   command=self._f5_refresh_emo_presets, width=3).pack(side=tk.LEFT, padx=(4, 0))
        # 打开 emotion_samples 文件夹
        ttk.Button(emo_ref_row, text="📂",
                   command=self._f5_open_samples_dir, width=3).pack(side=tk.LEFT, padx=(2, 0))
        # 清除
        ttk.Button(emo_ref_row, text="✕",
                   command=self._f5_clear_emo_ref, width=3).pack(side=tk.LEFT, padx=(2, 0))

        # 当前生效路径（只读展示）
        self._f5_emo_ref_path = tk.StringVar()
        self._f5_emo_ref_lbl = ttk.Label(emo_box,
                                          textvariable=self._f5_emo_ref_path,
                                          foreground="gray40",
                                          font=("微软雅黑", 8))
        self._f5_emo_ref_lbl.grid(row=2, column=0, columnspan=5, sticky=tk.W, pady=(2, 0))

        ttk.Label(emo_box,
                  text="提供一段带目标情感的音频，可增强情感迁移效果（不影响主参考音频的音色克隆）",
                  foreground="gray50", font=("微软雅黑", 8),
                  ).grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=(0, 0))

        # 预置内部数据：label → path
        self._f5_emo_preset_map: dict[str, str] = {}

        # 初次填充预置列表
        self._f5_emo_preset_combo.bind("<<ComboboxSelected>>", self._f5_on_emo_preset_selected)
        self.after(100, self._f5_refresh_emo_presets)   # 延迟到窗口渲染后再扫描

        # 情感预设变化时，自动更新 CFG 默认值
        def _on_emotion_change(*_):
            from f5_tts_engine import EMOTION_CFG_STRENGTH
            preset_cfg = EMOTION_CFG_STRENGTH.get(self._f5_emotion_var.get(), 2.0)
            self._f5_cfg_var.set(preset_cfg)
            # 情感切换视为参数变化，重置引擎
            self._f5_engine = None
        self._f5_emotion_combo.bind("<<ComboboxSelected>>", _on_emotion_change)

        # 按钮
        btns = ttk.Frame(f)
        btns.grid(row=6, column=0, sticky=tk.W, pady=(0, 4))
        self._f5_play = ttk.Button(btns, text="▶ 播放（克隆声音）", command=self._f5_play, width=18)
        self._f5_play.pack(side=tk.LEFT)
        self._f5_stop = ttk.Button(btns, text="⏹ 停止", command=self._f5_stop, width=12, state=tk.DISABLED)
        self._f5_stop.pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="💾 保存音频", command=self._f5_save).pack(side=tk.LEFT)
        ttk.Button(btns, text="🔄 重置引擎", command=self._f5_reset).pack(side=tk.LEFT, padx=(12, 0))

        # 提示标签 + 克隆质量评分
        hint_row = ttk.Frame(f)
        hint_row.grid(row=7, column=0, sticky=tk.W, pady=(0, 4), columnspan=2)
        self._f5_hint_lbl = ttk.Label(hint_row, text="", foreground="orange", font=("微软雅黑", 9))
        self._f5_hint_lbl.pack(side=tk.LEFT)
        self._f5_quality_lbl = ttk.Label(hint_row, text="", font=("微软雅黑", 9))
        self._f5_quality_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # 初始化引擎
        self._f5_engine = None
        self._f5_cached_ref_path = None   # 追踪当前引擎对应哪个 ref_audio
        self._f5_cached_ref_text = None   # 追踪当前引擎对应哪个 ref_text
        self._f5_cached_emotion = None    # 追踪当前情感预设
        self._f5_cached_emo_ref = None    # 追踪当前情感参考音频路径
        self._f5_rec_text = ""             # 录音朗读文本，防止 Text widget 清空后丢失

    def _f5_refresh_emo_presets(self):
        """扫描 emotion_samples/ 目录，更新情感参考音频预置下拉列表。"""
        try:
            from f5_tts_engine import list_emotion_samples, ensure_emotion_samples_dir
            ensure_emotion_samples_dir()          # 确保目录和 README 存在
            samples = list_emotion_samples()
        except Exception:
            samples = []

        # 构建 label → path 映射
        self._f5_emo_preset_map = {"— 不使用 —": ""}
        if samples:
            for s in samples:
                self._f5_emo_preset_map[s["label"]] = s["path"]
        else:
            self._f5_emo_preset_map["（暂无预置，点 📂 添加音频）"] = ""

        self._f5_emo_preset_combo["values"] = list(self._f5_emo_preset_map.keys())

        # 若当前选项已不在新列表中，重置为"不使用"
        if self._f5_emo_preset_var.get() not in self._f5_emo_preset_map:
            self._f5_emo_preset_var.set("— 不使用 —")
            self._f5_emo_ref_path.set("")

    def _f5_on_emo_preset_selected(self, _event=None):
        """用户从预置下拉选择情感参考音频。"""
        label = self._f5_emo_preset_var.get()
        path = self._f5_emo_preset_map.get(label, "")
        self._f5_emo_ref_path.set(path)
        if path:
            self._f5_engine = None   # 音频变了，重置引擎
            self._update_status(f"情感参考音频：{os.path.basename(path)}")
            # 尝试自动同步情感下拉
            try:
                from f5_tts_engine import list_emotion_samples
                for s in list_emotion_samples():
                    if s["path"] == path and s["emotion"]:
                        if self._f5_emotion_var.get() == "无（正常）":
                            self._f5_emotion_var.set(s["emotion"])
                            from f5_tts_engine import EMOTION_CFG_STRENGTH
                            self._f5_cfg_var.set(EMOTION_CFG_STRENGTH.get(s["emotion"], 2.0))
                        break
            except Exception:
                pass
        else:
            self._f5_emo_ref_path.set("")

    def _f5_browse_emo_ref(self):
        """自定义浏览情感参考音频。"""
        path = filedialog.askopenfilename(title="选择情感参考音频",
            filetypes=[("音频文件", "*.wav *.mp3 *.flac *.m4a"), ("所有文件", "*.*")])
        if path:
            self._f5_emo_ref_path.set(path)
            self._f5_emo_preset_var.set("— 自定义 —")   # 显示自定义标识
            self._f5_engine = None
            self._update_status(f"情感参考音频（自定义）：{os.path.basename(path)}")

    def _f5_clear_emo_ref(self):
        """清除情感参考音频。"""
        self._f5_emo_ref_path.set("")
        self._f5_emo_preset_var.set("— 不使用 —")
        self._f5_engine = None

    def _f5_open_samples_dir(self):
        """用文件管理器打开 emotion_samples 目录。"""
        try:
            from f5_tts_engine import ensure_emotion_samples_dir
            folder = ensure_emotion_samples_dir()
            import subprocess
            subprocess.Popen(f'explorer "{folder}"')
        except Exception as e:
            messagebox.showinfo("提示", f"无法打开目录：{e}")



    def _f5_browse_ref(self):
        path = filedialog.askopenfilename(title="选择参考音频",
            filetypes=[("音频文件", "*.wav *.mp3 *.flac *.m4a"), ("所有文件", "*.*")])
        if path:
            # 如果换了参考音频，清掉缓存引擎（强制重建），并清空 ref_text 提示
            if self._f5_engine is not None and self._f5_cached_ref_path != path:
                self._f5_engine = None
                self._f5_cached_ref_path = None
                self._f5_cached_ref_text = None
                self._update_status("已重置引擎（参考音频已更换），点击播放重新加载…")
            elif self._f5_engine is not None:
                self._update_status("当前引擎使用: " + os.path.basename(path))

            self._f5_ref_path.set(path)
            # 浏览已有文件时，同步更新_rec_text 缓存
            self._f5_rec_text = self._f5_ref_text.get("1.0", tk.END).strip()

    # ── F5-TTS 录音 ────────────────────────────────────────────────────────

    def _f5_toggle_record(self):
        """切换开始/停止录音"""
        if self._f5_recording:
            self._f5_stop_record()
        else:
            self._f5_start_record()

    def _f5_start_record(self):
        """启动录音"""
        ref_text = self._f5_ref_text.get("1.0", tk.END).strip()
        if not ref_text:
            messagebox.showwarning("提示", "请先在上方文本框输入你想朗读的文字，再开始录音。")
            return
        self._f5_rec_text = ref_text

        try:
            import sounddevice as sd
        except ImportError:
            messagebox.showerror("缺少依赖", "请先安装 sounddevice：\npip install sounddevice")
            return

        self._f5_recording = True
        self._f5_recording_frames = []
        self._f5_record_btn.config(text="⏹ 停止录音", style="Accent.TButton")
        self._f5_rec_status.config(text="● 录音中…", foreground="red")
        self._f5_quality_lbl.config(text="")
        self._update_status("正在录音，请朗读上方文本…")

        # 先清空波形
        self._f5_wave_canvas.delete("all")

        def _callback(indata, frames, time, status):
            if status:
                print(f"[录音] {status}")
            self._f5_recording_frames.append(indata.copy())
            # 在主线程更新音量条
            rms = float(np.sqrt(np.mean(indata ** 2)))
            peak = min(rms * 20, 1.0)
            self.after(0, lambda p=peak: self._f5_draw_wave_bar(p))

        try:
            # 16kHz 单声道，与 F5-TTS 训练采样率一致
            self._f5_recording_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32", callback=_callback
            )
            self._f5_recording_stream.start()
        except Exception as e:
            self._f5_recording = False
            self._f5_recording_frames = []
            self._f5_recording_stream = None
            self._f5_record_btn.config(text="🎤 开始录音")
            self._f5_rec_status.config(text="", foreground="gray")
            self.after(100, lambda err=str(e): messagebox.showerror("录音失败", err))

    def _f5_stop_record(self):
        """停止录音并保存"""
        if not self._f5_recording:
            return
        self._f5_recording = False

        if self._f5_recording_stream:
            self._f5_recording_stream.stop()
            self._f5_recording_stream = None

        self._f5_record_btn.config(text="🎤 开始录音")
        self._f5_rec_status.config(text="", foreground="gray")

        if not self._f5_recording_frames:
            self._update_status("录音为空")
            return

        # 拼接数据
        audio = np.concatenate(self._f5_recording_frames, axis=0).squeeze()
        duration = len(audio) / 16000

        # 检查录音时长（过短无法提取声音特征）
        if duration < 3.0:
            messagebox.showwarning("录音过短",
                f"录音仅 {duration:.1f} 秒，建议至少 5~10 秒以获得清晰的声音特征。\n"
                "请重新录音。")
            return

        # 检查音量是否过小（麦克风静音或增益过低）
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.005:
            messagebox.showwarning("录音过轻",
                "检测到录音音量过低，可能麦克风未正常收音或环境过于安静。\n"
                "请检查麦克风并重新录音。")
            return

        # 保存到临时文件
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        path = tmp.name
        audio_i16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        try:
            import soundfile as sf
            sf.write(path, audio_i16, 16000)
        except Exception:
            # soundfile 不可用时用 wave 标准库
            import wave
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_i16.tobytes())

        self._f5_ref_path.set(path)
        self._update_status(f"录音完成：{duration:.1f} 秒 → 已设为参考音频")

        # 音频变了，重置引擎
        self._f5_engine = None
        self._f5_cached_ref_path = None
        self._f5_cached_ref_text = None
        self._update_status(f"✅ 录音已设为参考音频（{duration:.1f}s），请输入目标文本后播放")

    def _f5_draw_wave_bar(self, peak):
        """绘制一根音量条（向右推进）"""
        cw, ch = 120, 24
        n = 12  # 条数
        bw = cw // n  # 每条宽度
        # 画满 n 条，每条高度与 peak 成正比
        self._f5_wave_canvas.delete("all")
        for i in range(n):
            bh = max(2, int(ch * peak * (0.4 + 0.6 * (i / n))))
            x0 = i * bw + 1
            x1 = x0 + bw - 2
            y0 = (ch - bh) // 2
            y1 = y0 + bh
            color = "#1a6" if peak > 0.3 else "#888"
            self._f5_wave_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def _f5_check_quality(self, ref_audio, generated_wav_path):
        """计算克隆质量（MEL 余弦相似度），在合成完成后调用"""
        try:
            import librosa
        except ImportError:
            return None

        try:
            # 加载参考音频（16kHz）
            ref_sig, _ = librosa.load(ref_audio, sr=16000, mono=True)
            # 加载生成音频
            gen_sig, _ = librosa.load(generated_wav_path, sr=16000, mono=True)

            # 对齐长度
            min_len = min(len(ref_sig), len(gen_sig))
            ref_sig = ref_sig[:min_len]
            gen_sig = gen_sig[:min_len]

            # 计算 mel 频谱
            ref_mel = librosa.feature.melspectrogram(y=ref_sig, sr=16000, n_mels=64)
            gen_mel = librosa.feature.melspectrogram(y=gen_sig, sr=16000, n_mels=64)

            # 转 dB
            ref_mel_db = librosa.power_to_db(ref_mel, ref=np.max)
            gen_mel_db = librosa.power_to_db(gen_mel, ref=np.max)

            # 取均值压缩为向量，计算余弦相似度
            ref_vec = ref_mel_db.mean(axis=1)
            gen_vec = gen_mel_db.mean(axis=1)

            cos_sim = float(np.dot(ref_vec, gen_vec) / (
                np.linalg.norm(ref_vec) * np.linalg.norm(gen_vec) + 1e-8
            ))
            return cos_sim
        except Exception:
            return None

    def _f5_reset(self):
        """重置 F5-TTS 引擎（清除模型缓存，换音频或文本后必须重置）"""
        # 录音中先停止
        if self._f5_recording:
            self._f5_recording = False
            if self._f5_recording_stream:
                self._f5_recording_stream.stop()
                self._f5_recording_stream = None
            self._f5_record_btn.config(text="🎤 开始录音")
            self._f5_rec_status.config(text="", foreground="gray")
        self._f5_engine = None
        self._f5_cached_ref_path = None
        self._f5_cached_ref_text = None
        self._f5_cached_emotion = None
        self._f5_cached_emo_ref = None
        self._f5_rec_text = ""
        self._f5_hint_lbl.config(text="")
        self._update_status("引擎已重置")

    def _f5_get_engine(self):
        ref_audio = self._f5_ref_path.get().strip()
        # 优先取录音时保存的文本，Text widget 可能已被清空
        ref_text = getattr(self, "_f5_rec_text", None)
        if not ref_text:
            ref_text = self._f5_ref_text.get("1.0", tk.END).strip()

        if not ref_audio:
            raise ValueError("请先选择参考音频文件！")
        if not ref_text:
            raise ValueError("请输入参考音频对应的文字 transcript！")

        emotion = self._f5_emotion_var.get()
        emo_ref = self._f5_emo_ref_path.get().strip() or None
        cfg = round(self._f5_cfg_var.get(), 2)

        # 任意参数变化时清缓存重建引擎
        if (self._f5_engine is not None
                and (self._f5_cached_ref_path != ref_audio
                     or self._f5_cached_ref_text != ref_text
                     or getattr(self, "_f5_cached_emotion", None) != emotion
                     or getattr(self, "_f5_cached_emo_ref", None) != emo_ref)):
            self._f5_engine = None

        if self._f5_engine is not None:
            # 仅更新可热更新参数（speed / nfe / cfg）
            self._f5_engine.speed = self._f5_speed_var.get()
            self._f5_engine.nfe_step = self._f5_nfe_var.get()
            self._f5_engine.cf_strength = cfg
            return self._f5_engine

        self._f5_engine = F5TTSEngine(
            ref_audio=ref_audio,
            ref_text=ref_text,
            speed=self._f5_speed_var.get(),
            nfe_step=self._f5_nfe_var.get(),
            cf_strength=cfg,
            emotion=emotion,
            emotion_ref_audio=emo_ref,
        )
        self._f5_cached_ref_path = ref_audio
        self._f5_cached_ref_text = ref_text
        self._f5_cached_emotion = emotion
        self._f5_cached_emo_ref = emo_ref
        self._f5_rec_text = ref_text
        return self._f5_engine

    def _f5_play(self):
        text = self._f5_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入要合成的文本")
            return
        self._f5_set_speaking(True)
        self._f5_hint_lbl.config(text="")

        def _on_progress(msg):
            # 从后台线程安全地更新 GUI 状态
            self.after(0, lambda: self._update_status("[加载] " + msg))

        def _run():
            try:
                engine = self._f5_get_engine()
                # 更新参数（每次播放都重新获取最新值）
                engine.speed = self._f5_speed_var.get()
                engine.nfe_step = self._f5_nfe_var.get()
                engine.speak(text, block=True, progress_callback=_on_progress)
                self.after(100, lambda: self._f5_set_speaking(False))
                self.after(100, lambda: self._update_status("✅ 播放完成"))
            except Exception as e:
                self.after(100, lambda: self._f5_set_speaking(False))
                self.after(100, lambda err=e: self._update_status(f"❌ 错误：{err}"))
                self.after(100, lambda err=e: messagebox.showerror("错误", str(err)))

        threading.Thread(target=_run, daemon=True).start()

    def _f5_stop(self):
        if self._f5_engine:
            self._f5_engine.stop()
        self._f5_set_speaking(False)
        self._update_status("已停止")

    def _f5_set_speaking(self, s):
        self._f5_play.config(state=tk.DISABLED if s else tk.NORMAL)
        self._f5_stop.config(state=tk.NORMAL if s else tk.DISABLED)

    def _f5_save(self):
        text = self._f5_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入文本")
            return
        path = filedialog.asksaveasfilename(title="保存音频", defaultextension=".wav",
            filetypes=[("WAV 音频", "*.wav"), ("MP3 音频", "*.mp3"), ("所有文件", "*.*")])
        if not path:
            return
        self._f5_hint_lbl.config(text="")
        self._f5_quality_lbl.config(text="")

        def _on_progress(msg):
            self.after(0, lambda: self._update_status("[加载] " + msg))

        def _run():
            try:
                self.after(0, lambda: self._update_status("正在合成并保存…"))
                engine = self._f5_get_engine()
                engine.speed = self._f5_speed_var.get()
                engine.nfe_step = self._f5_nfe_var.get()
                engine.save_to_file(text, path, progress_callback=_on_progress)
                self.after(0, lambda: self._update_status(f"已保存：{os.path.basename(path)}"))

                # 克隆质量评估
                ref_audio = self._f5_ref_path.get().strip()
                cos_sim = self._f5_check_quality(ref_audio, path)
                if cos_sim is not None:
                    if cos_sim > 0.75:
                        label, color = "🌟 高相似度", "#1a6"
                    elif cos_sim > 0.45:
                        label, color = "⚡ 中等相似度", "#c80"
                    else:
                        label, color = "🔧 相似度偏低", "#c00"
                    self.after(0, lambda l=label, c=color: self._f5_quality_lbl.config(
                        text=f"克隆质量 {l}  (cos={cos_sim:.3f})", foreground=c))
                else:
                    self.after(0, lambda: self._f5_quality_lbl.config(
                        text="（soundfile/librosa 未安装，无法评估克隆质量）", foreground="gray"))

                self.after(0, lambda: messagebox.showinfo("成功", f"已保存到：\n{path}"))
            except Exception as e:
                self.after(0, lambda err=e: messagebox.showerror("失败", str(err)))
                self.after(0, lambda: self._update_status("保存失败"))

        threading.Thread(target=_run, daemon=True).start()

    # ==================================================================
    # pyttsx3 标签页
    # ==================================================================

    def _build_pyttsx3_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        frame.columnconfigure(0, weight=1)
        return frame

    def _setup_pyttsx3_tab(self, engine):
        f = self._pyttsx3_tab

        info = ttk.Frame(f)
        info.grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        ttk.Label(info, text="引擎：pyttsx3（SAPI5，完全离线）", foreground="gray").pack(side=tk.LEFT)
        ttk.Label(info, text="💻 完全离线", foreground="gray30").pack(side=tk.RIGHT)

        ttk.Label(f, text="输入文本").grid(row=1, column=0, sticky=tk.W)
        text_frame = ttk.Frame(f)
        text_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=4)
        self._p3_text = tk.Text(text_frame, wrap=tk.WORD, font=("微软雅黑", 11), height=8)
        scrollbar = ttk.Scrollbar(text_frame, command=self._p3_text.yview)
        self._p3_text.configure(yscrollcommand=scrollbar.set)
        self._p3_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        toolbar = ttk.Frame(f)
        toolbar.grid(row=3, column=0, sticky=tk.W, pady=(0, 6))
        ttk.Button(toolbar, text="📂 导入文件", command=lambda: self._import_to(self._p3_text)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="🗑 清空", command=lambda: self._p3_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=6)

        ctrl = ttk.Frame(f)
        ctrl.grid(row=4, column=0, sticky=tk.EW, pady=(0, 6))
        ctrl.columnconfigure(1, weight=1)

        ttk.Label(ctrl, text="语速：").grid(row=0, column=0, sticky=tk.W)
        self._p3_rate_var = tk.IntVar(value=engine.rate)
        ttk.Scale(ctrl, from_=50, to=300, variable=self._p3_rate_var,
                  orient=tk.HORIZONTAL, command=lambda v: (
                      setattr(engine, 'rate', int(float(v))),
                      self._p3_rate_lbl.config(text=f"{engine.rate} 词/分")
                  )).grid(row=0, column=1, sticky=tk.EW, padx=4)
        self._p3_rate_lbl = ttk.Label(ctrl, text=f"{engine.rate} 词/分")
        self._p3_rate_lbl.grid(row=0, column=2, padx=(4, 0))

        btns = ttk.Frame(f)
        btns.grid(row=5, column=0, sticky=tk.W, pady=(0, 4))
        self._p3_play = ttk.Button(btns, text="▶ 播放", command=lambda: self._p3_do(engine, False), width=12)
        self._p3_play.pack(side=tk.LEFT)
        self._p3_stop = ttk.Button(btns, text="⏹ 停止", command=lambda: (engine.stop(), self._p3_set(False)), width=12, state=tk.DISABLED)
        self._p3_stop.pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="💾 保存音频", command=lambda: self._p3_do(engine, True)).pack(side=tk.LEFT)

    def _p3_do(self, engine, save):
        text = self._p3_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入文本")
            return
        self._p3_set(True)
        self._update_status("正在合成…" if not save else "正在合成并保存…")

        def _run():
            try:
                if save:
                    path = filedialog.asksaveasfilename(title="保存音频", defaultextension=".wav",
                        filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")])
                    if path:
                        engine.save_to_file(text, path)
                        self.after(100, lambda: messagebox.showinfo("成功", f"已保存到：\n{path}"))
                else:
                    engine.speak(text, block=True)
            except Exception as e:
                self.after(100, lambda: messagebox.showerror("错误", str(e)))
            finally:
                self.after(100, lambda: self._p3_set(False))
                self.after(100, lambda: self._update_status("就绪"))

        threading.Thread(target=_run, daemon=True).start()

    def _p3_set(self, s):
        self._p3_play.config(state=tk.DISABLED if s else tk.NORMAL)
        self._p3_stop.config(state=tk.NORMAL if s else tk.DISABLED)

    def _import_to(self, text_widget):
        path = filedialog.askopenfilename(title="导入文件",
            filetypes=[("PDF 文件", "*.pdf"), ("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        ext = path.lower().rsplit(".", 1)[-1]
        try:
            if ext == "pdf":
                from tts_engine import TTSEngine
                content = TTSEngine().read_pdf(path)
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
            else:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            text_widget.delete("1.0", tk.END)
            text_widget.insert("1.0", content)
            self._update_status(f"已导入：{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    # ==================================================================
    # 网络设置
    # ==================================================================

    def _show_network_settings(self):
        """打开网络设置对话框"""
        from edge_tts_engine import load_proxy_config, save_proxy_config

        dlg = tk.Toplevel(self)
        dlg.title("网络设置")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        # 居中
        dlg.update_idletasks()
        w, h = 420, 200
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # 代理模式
        cfg = load_proxy_config()
        use_system = tk.BooleanVar(value=cfg.get("use_system", False))
        ttk.Checkbutton(frame, text="使用系统代理", variable=use_system).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # 代理地址
        ttk.Label(frame, text="代理地址：").grid(row=1, column=0, sticky=tk.W)
        proxy_var = tk.StringVar(value=cfg.get("address", ""))
        proxy_entry = ttk.Entry(frame, textvariable=proxy_var, width=40)
        proxy_entry.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))

        hint = ttk.Label(frame, text="例：http://127.0.0.1:7890、socks5://127.0.0.1:1080",
                         foreground="gray")
        hint.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # 互斥联动：勾选系统代理时禁用手动输入
        def _toggle_system():
            state = tk.DISABLED if use_system.get() else tk.NORMAL
            proxy_entry.config(state=state)
            hint.config(foreground="gray" if use_system.get() else "gray")

        use_system.trace_add("write", lambda *_: _toggle_system())
        _toggle_system()

        # 提示文字
        tip = ttk.Label(frame, text="默认直连（不走代理），公司网络环境如需代理请配置。",
                        foreground="gray50", wraplength=380)
        tip.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))

        # 按钮
        btns = ttk.Frame(frame)
        btns.grid(row=5, column=0, columnspan=2, sticky=tk.E, pady=(6, 0))

        def _save():
            new_cfg = {
                "use_system": use_system.get(),
                "address": proxy_var.get().strip(),
            }
            save_proxy_config(new_cfg)

            # 更新引擎代理（三种模式）
            # "" = 直连（不走系统代理），None = 系统代理，"http://..." = 手动代理
            if use_system.get():
                proxy_val = None           # 系统代理：让 edge_tts 的 trust_env=True 生效
            else:
                addr = proxy_var.get().strip()
                proxy_val = addr if addr else ""   # 有值→手动代理，空→直连

            if USE_EDGE_TTS and hasattr(self, "_edge_engine"):
                self._edge_engine.proxy = proxy_val  # str or None
                # 刷新音色列表以验证连接
                self._edge_populate_voices()

            dlg.destroy()
            if use_system.get():
                mode = "系统代理"
            else:
                mode = proxy_var.get().strip() if proxy_var.get().strip() else "直连"
            self._update_status(f"网络设置已保存：{mode}")

        def _cancel():
            dlg.destroy()

        ttk.Button(btns, text="保存", command=_save, width=10).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="取消", command=_cancel, width=10).pack(side=tk.LEFT)

        dlg.bind("<Return>", lambda e: _save())
        dlg.bind("<Escape>", lambda e: _cancel())

    # ==================================================================
    # 状态
    # ==================================================================

    def _on_tab_changed(self, _event=None):
        """标签页切换时更新状态栏显示当前引擎信息"""
        tab_text = self.notebook.tab(self.notebook.select(), "text")
        if "Edge TTS" in tab_text:
            self._update_status("引擎：Edge TTS  |  🌐 需要网络")
        elif "F5-TTS" in tab_text:
            self._update_status("引擎：F5-TTS  |  💻 完全本地运行")
        elif "pyttsx3" in tab_text:
            self._update_status("引擎：pyttsx3  |  💻 完全离线")

    def _update_status(self, msg):
        self.status_var.set(f"  {msg}")


def main():
    app = TTSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
