"""
edge_tts_gui.py - Edge TTS GUI（tkinter，跨平台）
支持 50+ 音色、语速/音调/音量调节、PDF 导入

pip install edge-tts pymupdf -i https://pypi.tuna.tsinghua.edu.cn/simple --user
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from edge_tts_engine import EdgeTTSEngine


class TTSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Edge TTS 多音色朗读工具")
        self.resizable(True, True)
        self.minsize(620, 520)

        self.engine = EdgeTTSEngine()
        self._speaking = False

        self._build_ui()
        self._populate_voices()
        self._update_status("就绪")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── 顶部信息栏 ──────────────────────────────────────────
        info_frame = ttk.Frame(self, padding=(10, 6, 10, 0))
        info_frame.pack(fill=tk.X)
        info = EdgeTTSEngine.platform_info()
        ttk.Label(info_frame, text=f"后端：{info['backend']}（需要网络）",
                  foreground="gray").pack(side=tk.LEFT)

        # ── 文本输入区 ──────────────────────────────────────────
        text_frame = ttk.LabelFrame(self, text="输入文本", padding=8)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))

        self.text_area = tk.Text(
            text_frame, wrap=tk.WORD, font=("微软雅黑", 11), height=10
        )
        scrollbar = ttk.Scrollbar(text_frame, command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=scrollbar.set)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮行
        btn_frame = ttk.Frame(self, padding=(10, 0))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="PDF 导入",
                   command=self._import_pdf).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="TXT 导入",
                   command=self._import_txt).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="清空",
                   command=self._clear_text).pack(side=tk.LEFT)

        # ── 参数控制区 ──────────────────────────────────────────
        ctrl_frame = ttk.LabelFrame(self, text="朗读参数", padding=8)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        ctrl_frame.columnconfigure(1, weight=1)
        ctrl_frame.columnconfigure(3, weight=1)

        # 语速
        ttk.Label(ctrl_frame, text="语速：").grid(row=0, column=0, sticky=tk.W)
        self.rate_var = tk.IntVar(value=0)
        rate_scale = ttk.Scale(ctrl_frame, from_=-50, to=100,
                               variable=self.rate_var, orient=tk.HORIZONTAL,
                               command=self._on_rate_change)
        rate_scale.grid(row=0, column=1, sticky=tk.EW, padx=(4, 0))
        self.rate_label = ttk.Label(ctrl_frame, text="0（正常）")
        self.rate_label.grid(row=0, column=2, padx=(6, 20))

        # 音调
        ttk.Label(ctrl_frame, text="音调：").grid(row=0, column=3, sticky=tk.W)
        self.pitch_var = tk.IntVar(value=0)
        pitch_scale = ttk.Scale(ctrl_frame, from_=-50, to=50,
                                variable=self.pitch_var, orient=tk.HORIZONTAL,
                                command=self._on_pitch_change)
        pitch_scale.grid(row=0, column=4, sticky=tk.EW, padx=(4, 0))
        self.pitch_label = ttk.Label(ctrl_frame, text="0 Hz")
        self.pitch_label.grid(row=0, column=5, padx=(6, 0))

        # 音量
        ttk.Label(ctrl_frame, text="音量：").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.volume_var = tk.DoubleVar(value=1.0)
        vol_scale = ttk.Scale(ctrl_frame, from_=0.0, to=2.0,
                              variable=self.volume_var, orient=tk.HORIZONTAL,
                              command=self._on_volume_change)
        vol_scale.grid(row=1, column=1, sticky=tk.EW, padx=(4, 0))
        self.vol_label = ttk.Label(ctrl_frame, text="100%")
        self.vol_label.grid(row=1, column=2, padx=(6, 20))

        # 音色选择
        ttk.Label(ctrl_frame, text="音色：").grid(row=1, column=3, sticky=tk.W, pady=(6, 0))
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(
            ctrl_frame, textvariable=self.voice_var,
            state="readonly", width=34
        )
        self.voice_combo.grid(row=1, column=4, columnspan=2,
                              sticky=tk.W, pady=(6, 0), padx=(4, 0))
        self.voice_combo.bind("<<ComboboxSelected>>", self._on_voice_change)

        # ── 操作按钮区 ──────────────────────────────────────────
        action_frame = ttk.Frame(self, padding=(10, 6, 10, 6))
        action_frame.pack(fill=tk.X)

        self.play_btn = ttk.Button(action_frame, text="播放",
                                   command=self._play, width=12)
        self.play_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(action_frame, text="停止",
                                  command=self._stop, width=12, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=6)

        ttk.Button(action_frame, text="保存为 MP3",
                   command=self._save_mp3, width=14).pack(side=tk.LEFT)

        # ── 状态栏 ──────────────────────────────────────────────
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=(8, 2))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    # ------------------------------------------------------------------
    # 音色列表
    # ------------------------------------------------------------------

    def _populate_voices(self):
        voices = self.engine.list_voices("zh")
        # 按 ShortName 显示
        display = [f"{v['short_name']} [{v['gender']}] {v['name'].split('(')[-1].rstrip(')')}"
                   if '(' in v['name'] else f"{v['short_name']} [{v['gender']}] {v['name']}"
                   for v in voices]
        self._all_voices = voices
        self.voice_combo["values"] = display
        if display:
            self.voice_combo.current(0)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_rate_change(self, val):
        r = int(float(val))
        self.engine.rate = r
        self.rate_label.config(text=f"{r:+d}（正常）" if r == 0 else f"{r:+d}")

    def _on_pitch_change(self, val):
        p = int(float(val))
        self.engine.pitch = p
        self.pitch_label.config(text=f"{p:+d} Hz")

    def _on_volume_change(self, val):
        v = round(float(val), 2)
        self.engine.volume = v
        self.vol_label.config(text=f"{int(v * 100)}%")

    def _on_voice_change(self, _event=None):
        idx = self.voice_combo.current()
        if 0 <= idx < len(self._all_voices):
            self.engine.voice = self._all_voices[idx]["short_name"]

    def _play(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入要朗读的文本！")
            return
        self._set_speaking(True)
        self._update_status("正在合成并播放...")

        def _done():
            self.after(100, lambda: self._set_speaking(False))
            self.after(100, lambda: self._update_status("就绪"))

        def _thread():
            self.engine.speak(text, block=True)
            _done()

        threading.Thread(target=_thread, daemon=True).start()

    def _stop(self):
        self.engine.stop()
        self._set_speaking(False)
        self._update_status("已停止")

    def _import_pdf(self):
        path = filedialog.askopenfilename(
            title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf")]
        )
        if not path:
            return
        try:
            content = self.engine.read_pdf(path)
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            content = content.strip()
            if not content:
                messagebox.showerror("读取失败", "PDF 中未提取到文字（可能是扫描版）")
                return
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", content)
            self._update_status(f"PDF 导入成功（{len(content)} 字）：{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    def _import_txt(self):
        path = filedialog.askopenfilename(
            title="选择文本文件", filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", content)
            self._update_status(f"已导入：{os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    def _clear_text(self):
        self.text_area.delete("1.0", tk.END)

    def _save_mp3(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请先输入要转换的文本！")
            return
        path = filedialog.asksaveasfilename(
            title="保存 MP3", defaultextension=".mp3",
            filetypes=[("MP3 音频", "*.mp3")]
        )
        if not path:
            return
        try:
            self._update_status("正在合成...")
            self.engine.save_to_file(text, path)
            self._update_status("就绪")
            messagebox.showinfo("保存成功", f"已保存：\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            self._update_status("保存失败")

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------

    def _set_speaking(self, speaking: bool):
        self._speaking = speaking
        self.play_btn.config(state=tk.DISABLED if speaking else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if speaking else tk.DISABLED)

    def _update_status(self, msg: str):
        self.status_var.set(f"  {msg}")


def main():
    app = TTSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
