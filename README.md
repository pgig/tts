# TTS Tool — 跨平台文本转语音工具

双引擎 GUI：**Edge TTS**（微软云端，多音色）+ **F5-TTS**（本地声音克隆）。离线环境下自动降级为 **pyttsx3**（SAPI5）。

---

## 文件结构

```
tts/
├── tts_gui.py          # tkinter GUI 主界面（Edge TTS + F5-TTS 双标签页）
├── tts_cli.py          # 命令行接口
├── edge_tts_engine.py  # Edge TTS 引擎（微软神经网络，50+ 音色）
├── edge_tts_cli.py     # Edge TTS 独立 CLI
├── f5_tts_engine.py    # F5-TTS 声音克隆引擎（CFM 模型，本地推理）
├── tts_engine.py       # pyttsx3 核心引擎（本地 SAPI5，修复二次播放 bug）
├── requirements.txt    # Python 依赖
└── README.md
```

---

## 安装依赖

```bash
# Edge TTS（推荐，云端合成）
pip install edge-tts pygame -i https://pypi.tuna.tsinghua.edu.cn/simple --user

# F5-TTS（本地声音克隆，需 CUDA GPU）
pip install f5-tts torch torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple --user

# PDF 支持
pip install pymupdf -i https://pypi.tuna.tsinghua.edu.cn/simple --user    # 推荐，速度快

# 扫描件 PDF OCR（可选，自动识别图片型 PDF）
pip install rapidocr_onnxruntime -i https://pypi.tuna.tsinghua.edu.cn/simple --user

# PDF 支持（备用后端）

# pyttsx3（离线 SAPI5 回退）
pip install pyttsx3 -i https://pypi.tuna.tsinghua.edu.cn/simple --user
```

> **Linux 额外依赖**（pyttsx3 后端）：
> ```bash
> sudo apt-get install espeak
> ```

---

## GUI 使用

```bash
python tts_gui.py
```

### 标签页

| 标签页 | 引擎 | 特点 |
|--------|------|------|
| **Edge TTS 云端合成** | 微软神经网络 | 50+ 音色，语速/音调/音量可调，需联网 |
| **F5-TTS 声音克隆** | CFM 连续流匹配 | 5 秒参考音频克隆任意声音，本地 GPU 推理，支持情感风格控制 |

> **离线回退**：若 Edge TTS 和 F5-TTS 均 import 不可用，启动时自动显示 pyttsx3 离线标签页。若 Edge TTS 运行时遇到网络错误（断网/超时），会自动降级到 pyttsx3 并切换标签页，无需手动操作。

### 通用功能
- 文本输入框（支持粘贴、从文件导入）
- **支持导入 PDF 文件**（文字型 PDF 直接提取，扫描件自动 OCR 识别）
  - 扫描件导入在后台线程执行，状态栏显示逐页进度
- 语言/音色切换下拉
- 语速 / 音调 / 音量滑块
- 播放 / 停止按钮
- **保存为音频文件**（带实时进度显示）
- F5-TTS：内置录音采集参考音频 + 克隆质量评估（余弦相似度）
- F5-TTS：**情感风格控制**（开心 / 悲伤 / 愤怒 / 惊讶等 9 种预设，支持情感参考音频）
- **网络设置**（直连 / 系统代理 / 手动代理，菜单栏「设置→网络设置」）
- **状态栏**跟随当前标签页自动切换引擎信息

### F5-TTS 使用流程

1. 上传或录制参考音频（5~10 秒即可）
2. 输入目标文本
3. 选择情感预设（可选：开心 / 悲伤 / 愤怒 / 兴奋等，默认无情感）
4. 可选上传「情感参考音频」增强情感迁移（不影响主参考音频的音色克隆）
5. 调整语速 / 推理步数 / 情感强度
6. 点击播放或保存

> **情感控制原理**：通过在目标文本前注入情感标记词（如 `[开心]`）引导模型风格，不需要额外微调模型。情感强度（CFG）越高表现力越强，建议范围 2.0~4.0。

> **GPU 要求**：GTX 1650 4GB 可运行（fp32 模式约 1.7GB 显存）。
> 首次使用会自动下载模型（约 1.1GB）。

---

## CLI 使用

```bash
# 直接朗读文本（Edge TTS）
python tts_cli.py -t "你好，世界"

# 指定音色
python tts_cli.py -t "你好" --voice zh-CN-YunxiNeural    # 云希，男声
python tts_cli.py -t "你好" --voice zh-CN-XiaoxiaoNeural # 晓晓，女声（默认）

# 列出所有可用音色
python tts_cli.py --list-voices

# 读取文本文件 / PDF
python tts_cli.py -f input.txt
python tts_cli.py -f document.pdf

# 语速（-100 ~ +100）、音调（-50Hz ~ +50Hz）、音量（0.0 ~ 2.0）
python tts_cli.py -t "Hello" --rate 20 --pitch 10 --volume 1.2

# 保存为音频文件（不播放，带进度回调）
python tts_cli.py -t "保存测试" -o output.mp3

# 管道输入
echo "pipe test" | python tts_cli.py

# 查看平台后端信息
python tts_cli.py --platform
```

### CLI 参数一览

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-t TEXT` | 直接传入文本 | — |
| `-f FILE` | 从文件读取（自动识别 .pdf / .txt） | — |
| `--voice VOICE` | Edge TTS 音色 short_name | zh-CN-XiaoxiaoNeural |
| `--rate N` | 语速偏移（-100 ~ +100） | 0 |
| `--pitch N` | 音调偏移（-50 ~ +50 Hz） | 0 |
| `--volume N` | 音量（0.0 ~ 2.0） | 1.0 |
| `-o FILE` | 保存音频文件 | — |
| `--list-voices` | 列出所有可用音色 | — |
| `--platform` | 显示平台/后端信息 | — |

---

## 中文音色一览（Edge TTS）

| short_name | 性别 | 方言/风格 |
|------------|------|-----------|
| zh-CN-XiaoxiaoNeural | 女 | 标准普通话（默认） |
| zh-CN-YunjianNeural | 男 | 标准普通话 |
| zh-CN-YunxiNeural | 男 | 青年男声 |
| zh-CN-YunxiaNeural | 男 | 少年男声 |
| zh-CN-YunyangNeural | 男 | 播音员风格 |
| zh-CN-XiaoyiNeural | 女 | 青年女声 |
| zh-CN-shaanxi-XiaoniNeural | 女 | 陕西话 |
| zh-CN-liaoning-XiaobeiNeural | 女 | 东北话 |
| zh-TW-HsiaoChenNeural | 女 | 台湾普通话 |
| zh-TW-YunJheNeural | 男 | 台湾普通话 |
| zh-HK-HiuGaaiNeural | 女 | 粤语 |
| zh-HK-WanLungNeural | 男 | 粤语 |

> 更多音色（英文、日文、韩文等）运行 `python tts_cli.py --list-voices` 查看。

---

## 跨平台支持

| 系统 | Edge TTS | F5-TTS | pyttsx3 |
|------|----------|--------|---------|
| Windows | ✅ 需联网 | ✅ 需 CUDA GPU | ✅ SAPI5 |
| macOS | ✅ 需联网 | ✅ 需 MPS/CUDA | ✅ NSSpeechSynthesizer |
| Linux | ✅ 需联网 | ✅ 需 CUDA GPU | ✅ espeak |

---

## 已知问题与修复

### Windows SAPI5 第二次播放无声音（pyttsx3）

**原因**：pyttsx3 在同一进程内重用 `Engine` 实例时，SAPI5 COM 状态未正确重置。

**修复**：每次 `speak()` 调用都重新 `pyttsx3.init()` 创建新引擎实例，播放结束后立即 `del`。

### Edge TTS 代理超时崩溃

**原因**：Windows 注册表残留 PAC 自动配置，`aiohttp.ClientSession(trust_env=True)` 检测到代理不通导致 TLS 握手超时。

**修复**：通过 `edge-tts` 原生 `proxy` 参数传递，支持三种模式：`""` 直连、`None` 系统代理、`"http://..."` 手动代理。GUI 菜单栏「设置→网络设置」可切换，配置持久化到 `tts_config.json`。

### F5-TTS float16 生成全 NaN 音频

**原因**：F5-TTS 的 `load_checkpoint` 在 GPU 算力 ≥ 7 时自动将模型转为 float16，导致 CFM 推理产生 18.4% NaN。

**修复**：加载模型后检测 dtype，强制 `model.float()` 回 fp32。GTX 1650 4GB 足够（~1.7GB 显存）。

### Edge TTS / F5-TTS 保存无进度

**修复**：用 `stream()` 逐块写入替代 `communicate.save()`，每 4 个数据块回调进度。GUI 改为后台线程执行，不再阻塞主线程。

### 扫描件 PDF 导入为空

**原因**：扫描件 PDF 内嵌的是图片而非文字层，PyMuPDF 的 `get_text()` 无法提取。

**修复**：自动检测扫描件（全部页面无可提取文字时），启动 RapidOCR 兜底识别。PDF 导入改为后台线程，状态栏实时显示「正在 OCR 识别…（N/M 页）」，导入期间按钮禁用防重复。

### Edge TTS 断网无降级

**原因**：原实现仅在 import 阶段判断引擎可用性，运行时 Edge TTS 网络失败只会报错，不会自动切换。

**修复**：`speak()` / `save_to_file()` 捕获网络异常后，自动创建 pyttsx3 离线标签页、复制当前文本并切换过去，弹窗提示用户。音色加载失败时状态栏也会提前警告网络异常。

### F5-TTS 输出开头出现参考音频内容

**原因**：F5-TTS 推理时输入为 `ref_text + gen_text`，生成的 mel 频谱前半部分对应参考音频。官方代码用 `ref_audio_len`（hop_length 对齐）跳过，但由于参考音频时长与文字字数比的估算误差，参考音频末尾内容会泄漏到输出开头。

**修复**：推理完成后，根据参考音频实际采样点数 + 0.3 秒安全余量截掉输出开头，确保参考音频内容不泄漏。

### 状态栏显示与当前标签页不一致

**原因**：状态栏仅在启动时设置一次引擎信息，切换标签页后不会更新。

**修复**：绑定 `<<NotebookTabChanged>>` 事件，切换标签页时自动刷新状态栏显示对应引擎信息。
