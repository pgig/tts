# TTS Tool 功能清单

> **维护规则**：每次变更功能后，逐项检查是否影响到已有功能点，在「影响记录」列追加。
> 如果检查无影响，标注 `✅ 无影响`；如果有影响，标注 `⚠️ 影响` 并描述。

---

## 一、Edge TTS 引擎 (`edge_tts_engine.py`)

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| E1 | 初始化引擎（指定音色/语速/音调/音量/代理） | `EdgeTTSEngine.__init__()` L65-80 | ✅ | |
| E2 | 代理配置持久化（`tts_config.json` 读写） | `load_proxy_config()` / `save_proxy_config()` L30-53 | ✅ | |
| E3 | 三种代理模式：直连`""` / 系统代理`None` / 手动代理 | `self.proxy` 语义，`_synthesize()` / `_synthesize_to_mp3()` L166-172, L280-286 | ✅ | |
| E4 | 列出可用音色（按语言过滤） | `list_voices(lang, proxy)` L86-119 | ✅ | |
| E5 | 平台信息查询 | `platform_info()` L121-127 | ✅ | |
| E6 | 播放状态轮询 | `is_speaking` 属性 L133-138 | ✅ | |
| E7 | voices 列表兼容接口 | `voices` 属性 L140-143 | ✅ | |
| E8 | 语速/音调/音量字符串转换（从 self 属性读取） | `_rate_str()` / `_pitch_str()` / `_volume_str()` L149-161 | ✅ | |
| E9 | 异步合成音频（内存 BytesIO） | `_synthesize(text, output_path=None)` L163-192 | ✅ | |
| E10 | 异步合成 MP3 文件（带进度回调） | `_synthesize_to_mp3()` L277-297 | ✅ | |
| E11 | 合成并播放（同步/异步 + pygame 纯内存播放） | `speak(text, block, on_done)` L194-243 | ✅ | |
| E12 | 停止播放 | `stop()` L245-249 | ✅ | |
| E13 | 保存音频文件（自动区分 .mp3 / .wav） | `save_to_file(text, output_path, progress_callback)` L251-275 | ✅ | |
| E14 | PDF 文本提取（PyMuPDF + RapidOCR 扫描件兜底） | `read_pdf(source, progress_callback)` / `_ocr_page()` / `pdf_backend_name()` L304-372 | ✅ | |
| E15 | asyncio.new_event_loop() 隔离（后台线程） | `speak()` / `save_to_file()` / `list_voices()` | ✅ | |

---

## 二、F5-TTS 引擎 (`f5_tts_engine.py`)

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| F1 | 引擎初始化（参考音频/文本/语速/推理步数） | `F5TTSEngine.__init__()` L235-264 | ✅ | |
| F2 | 参考音频预处理（重采样/格式化/音量归一化） | `_preprocess_ref()` L270-315 | ✅ | |
| F3 | 模型懒加载（首次使用时从 ModelScope 下载） | `_load_f5_tts(progress_callback)` L92-188 | ✅ | |
| F4 | float16→float32 修复（解决 NaN 问题） | `_load_f5_tts()` L168-171 | ✅ | |
| F5 | VocoderOffloadProxy（4GB 显存优化） | `_VocoderOffloadProxy` 类 L191-220 | ✅ | |
| F6 | vocoder monkey-patch（推理时 offload 到 CPU） | `_generate_audio()` L347-373 | ✅ | |
| F7 | NaN/Inf 自动修复（线性插值） | `_generate_audio()` L401-451 | ✅ | |
| F8 | 合成音频并播放（pygame） | `speak(text, block, progress_callback)` L459-521 | ✅ | |
| F9 | 停止播放（线程锁 + 标志位） | `stop()` / `is_speaking` L523-533 | ✅ | |
| F10 | 保存音频文件（.wav / .mp3 via pydub） | `save_to_file(text, output_path, progress_callback)` L539-569 | ✅ | |
| F11 | ffmpeg 路径检测（imageio-ffmpeg 优先） | `_get_ffmpeg_path()` L70-89 | ✅ | |

---

## 三、pyttsx3 引擎 (`tts_engine.py`)

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| P1 | 引擎初始化（读取系统声音列表） | `TTSEngine.__init__()` L98-113 | ✅ | |
| P2 | 子进程 TTS 方案（真正可中断播放） | `_spawn_tts()` L140-161 | ✅ | |
| P3 | 同步/异步朗读 | `speak(text, block, on_done)` L163-208 | ✅ | |
| P4 | 停止播放（TASKKILL / SIGTERM） | `stop()` L210-230 | ✅ | |
| P5 | 保存音频文件 | `save_to_file(text, output_path, on_done)` L286-323 | ✅ | |
| P6 | PDF 文本提取（PyMuPDF / PyPDF2 双后端） | `read_pdf(filepath, max_pages)` L236-274 | ✅ | |
| P7 | 文件朗读（自动识别 PDF/纯文本） | `speak_file(filepath)` L276-284 | ✅ | |
| P8 | PDF 后端检测 | `pdf_backend_name()` L329-331 | ✅ | |
| P9 | 平台信息查询 | `platform_info()` L333-340 | ✅ | |
| P10 | 播放完成回调 | `set_done_callback(cb)` L132-134 | ✅ | |

---

## 四、GUI 主程序 (`tts_gui.py`)

### 4.1 通用

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| G1 | 引擎自动选择（优先 Edge TTS > F5-TTS > pyttsx3） | L26-49 | ✅ | |
| G2 | 菜单栏「设置→网络设置」 | L64-68 | ✅ | |
| G3 | 状态栏信息显示 | `_update_status()` L965-966 | ✅ | |

### 4.2 Edge TTS 标签页

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| GE1 | 文本输入框（8行高，微软雅黑字体） | L130-137 | ✅ | |
| GE2 | 导入文件（PDF 后台线程 OCR + TXT 主线程） | `_edge_import()` L259-315 | ✅ | |
| GE3 | 清空文本按钮 | L143 | ✅ | |
| GE4 | 音色语言切换（中文/粤语/台湾/英文） | L148-152 | ✅ | |
| GE5 | 音色 Combobox（后台线程加载，防阻塞） | `_edge_populate_voices()` / `_edge_apply_voices()` L189-217 | ✅ | |
| GE6 | 语言切换竞态保护（丢弃过期结果） | `_edge_apply_voices()` L206-208 | ✅ | |
| GE7 | 语速滑块（-100 ~ +100） | L166-171 | ✅ | |
| GE8 | 音调滑块（-50 ~ +50 Hz） | L173-178 | ✅ | |
| GE9 | 播放按钮（后台线程，防 GUI 阻塞） | `_edge_play()` L234-247 | ✅ | |
| GE10 | 停止按钮 | `_edge_stop()` L249-252 | ✅ | |
| GE11 | 保存音频（MP3/WAV，带进度回调） | `_edge_save()` L278-305 | ✅ | |
| GE12 | 引擎初始化时读取代理配置 | L78-86 | ✅ | |

### 4.3 F5-TTS 标签页

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| GF1 | 参考音频浏览选择 | `_f5_browse_ref()` L440-455 | ✅ | |
| GF2 | 参考音频麦克风录制（sounddevice） | `_f5_start_record()` / `_f5_stop_record()` L466-573 | ✅ | |
| GF3 | 录音波形/音量指示（Canvas 动态条） | `_f5_draw_wave_bar()` L575-589 | ✅ | |
| GF4 | 录音时长检查（≥3 秒） | L535-539 | ✅ | |
| GF5 | 录音音量检查（防静音） | L541-547 | ✅ | |
| GF6 | 目标文本输入框 | L384-391 | ✅ | |
| GF7 | 语速滑块（0.5x ~ 2.0x） | L398-403 | ✅ | |
| GF8 | 推理步数滑块（16 ~ 64） | L405-410 | ✅ | |
| GF9 | 播放按钮（懒加载引擎，缓存机制） | `_f5_play()` / `_f5_get_engine()` L677-703, L645-675 | ✅ | |
| GF10 | 停止按钮 | `_f5_stop()` L705-709 | ✅ | |
| GF11 | 保存音频（WAV/MP3，带克隆质量评分） | `_f5_save()` L715-760 | ✅ | |
| GF12 | 克隆质量评估（MEL 余弦相似度） | `_f5_check_quality()` L591-626 | ✅ | |
| GF13 | 引擎重置（清除模型缓存） | `_f5_reset()` L628-643 | ✅ | |
| GF14 | 参考音频/文本变更自动重置引擎 | `_f5_get_engine()` L657-661 | ✅ | |
| GF15 | 录音文本缓存（防 Text widget 清空后丢失） | `_f5_rec_text` 机制 | ✅ | |

### 4.4 pyttsx3 标签页

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| GP1 | 文本输入框 | L779-786 | ✅ | |
| GP2 | 导入文件（PDF/TXT，调用 TTSEngine.read_pdf） | `_import_to()` L845-864 | ✅ | |
| GP3 | 清空文本按钮 | L791 | ✅ | |
| GP4 | 语速滑块（50 ~ 300 词/分） | L797-805 | ✅ | |
| GP5 | 播放/停止/保存按钮 | L808-813 | ✅ | |

### 4.5 网络设置对话框

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| GN1 | 代理模式选择（系统代理/手动代理/直连） | `_show_network_settings()` L870-959 | ✅ | |
| GN2 | 系统代理 checkbox 联动（勾选时禁用手动输入） | L907-914 | ✅ | |
| GN3 | 代理地址输入 + 示例提示 | L898-905 | ✅ | |
| GN4 | 保存代理配置到 `tts_config.json` | `_save()` L925-950 | ✅ | |
| GN5 | 保存后刷新音色列表验证连接 | `_save()` L943 | ✅ | |
| GN6 | Enter 保存 / Escape 取消 | L958-959 | ✅ | |

---

## 五、命令行工具

### 5.1 Edge TTS CLI (`edge_tts_cli.py`)

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| CE1 | 直接文本朗读 | `-t "文本"` L79-80, L102-104 | ✅ | |
| CE2 | 文件朗读（PDF/TXT） | `-f file` L64-78 | ✅ | |
| CE3 | 保存为 MP3 | `-o output.mp3` L97-101 | ✅ | |
| CE4 | 指定音色/语速/音调/音量 | `-v` / `-r` / `-p` / `--vol` L34-42, L87-94 | ✅ | |
| CE5 | 列出音色 | `--list-voices [lang]` L43-61 | ✅ | |

### 5.2 多引擎 CLI (`tts_cli.py`)

| # | 功能点 | 接口/代码位置 | 状态 | 影响记录 |
|---|--------|--------------|------|----------|
| CM1 | 引擎切换（edge-tts / f5-tts / pyttsx3） | `--engine` L54-56, L130-147 | ✅ | |
| CM2 | 文本/文件/PDF/stdin 输入 | `-t` / `-f` / stdin L191-222 | ✅ | |
| CM3 | F5-TTS 声音克隆参数 | `--ref-audio` / `--ref-text` / `--speed` / `--nfe` L105-120 | ✅ | |
| CM4 | 保存音频 / 直接朗读 | `-o` / 默认播放 L242-252 | ✅ | |
| CM5 | 列出音色 | `--list-voices` L174-189 | ✅ | |
| CM6 | 平台信息查询 | `--platform` L167-172 | ✅ | |

---

## 六、引擎间隔离性

| 引擎对 | 是否隔离 | 说明 |
|--------|---------|------|
| Edge TTS ↔ F5-TTS | ✅ 完全隔离 | 无共享状态，无交叉引用 |
| Edge TTS ↔ pyttsx3 | ⚠️ 部分共享 | 共用 `pygame.mixer`（双 init 不报错），pyttsx3 的 PDF 导入用 `TTSEngine().read_pdf()` |
| F5-TTS ↔ pyttsx3 | ⚠️ 部分共享 | 共用 `pygame.mixer`，F5-TTS 无 PDF 功能 |

---

## 变更日志

| 日期 | 变更内容 | 影响的功能点 | 影响评估 |
|------|---------|-------------|---------|
| 2026-04-26 | proxy 三种模式语义修正（`""`=直连, `None`=系统代理, `"http://..."`=手动代理） | E1, E3, E4, E9, E10, E13, E15, GE5, GN1, GN4, GN5, CE5 | ✅ 已验证 |
| 2026-04-26 | GUI 引擎初始化读取 `tts_config.json` 配置 | GE12 | ✅ 新增功能 |
| 2026-04-26 | 创建功能清单文件 | — | — |
| 2026-04-26 | 扫描件 PDF OCR 支持（RapidOCR 兜底 + 后台线程导入 + 逐页进度） | E14, GE2 | ✅ 新增功能 |
