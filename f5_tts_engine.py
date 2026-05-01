"""
f5_tts_engine.py - F5-TTS 声音克隆引擎（本地推理）

pip install f5-tts imageio-ffmpeg --user -i https://pypi.tuna.tsinghua.edu.cn/simple

F5-TTS 核心特性：
  - 零样本声音克隆：提供 10~30 秒参考音频即可克隆任意声音
  - 完全本地运行：无网络依赖，模型下载后离线可用
  - 音质优秀：基于流匹配的非自回归 TTS

使用前提：
  - ref_audio：参考音频文件路径（.wav/.mp3/.flac，推荐 16kHz+）
  - ref_text：参考音频对应的文字 transcript（必须与音频内容完全一致）
  - gen_text：要合成的目标文本

示例初始化：
  engine = F5TTSEngine(
      ref_audio="my_voice.wav",
      ref_text="这是我自己的声音，用来克隆这段文字。",
  )
  engine.speak("你好，这是一段由 F5-TTS 克隆声音生成的语音。")
"""

import gc
import io
import os
import shutil
import soundfile as sf
import sys
import tempfile
import threading

import numpy as np
import pygame
import torch

# ── 4GB 显存优化：CUDA 内存分配策略 ──────────────────────────────
# 注意：expandable_segments 在 Windows PyTorch 上不支持（会触发 warning），暂不设置
# 如需 Linux 环境下启用，取消下行注释：
# if torch.cuda.is_available():
#     os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torchaudio
from tqdm import tqdm

pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=512)

# 让 pydub 找到 imageio-ffmpeg 绑定的 ffmpeg
import imageio_ffmpeg
import os as _os
_os.environ["PATH"] = _os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe()) + _os.pathsep + _os.environ.get("PATH", "")

import f5_tts  # noqa: E402 触发命名空间包初始化

# 延迟导入，模型太大，首次使用时才加载
_f5_tts_installed = False
_f5_tts_model = None
_f5_tts_vocoder = None


def _check_f5_tts():
    global _f5_tts_installed
    try:
        import f5_tts
        return True
    except ImportError:
        return False


def _get_ffmpeg_path():
    """获取 ffmpeg 路径（优先用 imageio-ffmpeg 绑定的）"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.isfile(exe):
            return exe
    except ImportError:
        pass

    # 尝试 PATH 中的 ffmpeg
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        return ffmpeg_in_path

    raise RuntimeError(
        "ffmpeg 未找到！请安装 imageio-ffmpeg（推荐）：\n"
        "  pip install imageio-ffmpeg --user -i https://pypi.tuna.tsinghua.edu.cn/simple\n"
        "或手动安装 ffmpeg 后加入 PATH"
    )


def _load_f5_tts(progress_callback=None):
    """懒加载 F5-TTS 模型（首次调用时下载/加载）

    :param progress_callback: 可选回调函数，每阶段调用一次，传入阶段描述字符串。
                              用于 GUI 实时显示加载进度。
    """
    global _f5_tts_model, _f5_tts_vocoder

    if _f5_tts_model is not None:
        progress_callback and progress_callback("[F5-TTS] 模型已加载（缓存）")
        return _f5_tts_model, _f5_tts_vocoder

    def _p(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    import glob, os
    from importlib.resources import files
    from f5_tts.infer.utils_infer import device, load_model, load_vocoder
    from f5_tts.model import CFM
    from hydra.utils import get_class
    from omegaconf import OmegaConf

    model_name = "F5TTS_Base"
    vocoder_name = "vocos"

    # 加载配置
    config_path = str(files("f5_tts").joinpath(f"configs/{model_name}.yaml"))
    model_cfg = OmegaConf.load(config_path)
    model_cls = get_class(f"f5_tts.model.{model_cfg.model.backbone}")
    model_arc = model_cfg.model.arch

    # f5_tts 命名空间包路径
    import f5_tts as _f5pkg
    _pkg_dir = list(_f5pkg.__path__)[0]
    _examples_dir = os.path.join(_pkg_dir, "infer", "examples")

    # 查找已有模型文件（safetensors 或 pt）
    _existing = (
        glob.glob(os.path.join(_examples_dir, "**", "model_1200000.safetensors"), recursive=True) or
        glob.glob(os.path.join(_examples_dir, "**", "model_1200000.pt"), recursive=True) or
        glob.glob(os.path.join(_examples_dir, "**", "model_1250000.safetensors"), recursive=True) or
        glob.glob(os.path.join(_examples_dir, "**", "model_1250000.pt"), recursive=True)
    )

    if _existing:
        ckpt_path = _existing[0]
        _p(f"[F5-TTS] 使用已有模型: {os.path.basename(ckpt_path)}")
    else:
        from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
        _p("[F5-TTS] 模型未找到，从 ModelScope 下载…")
        _local = ms_snapshot_download("SWivid/F5-TTS_Emilia-ZH-EN", cache_dir=_examples_dir)
        _found = glob.glob(os.path.join(_local, "**", "*.safetensors"), recursive=True) or \
                 glob.glob(os.path.join(_local, "**", "*.pt"), recursive=True)
        if not _found:
            raise FileNotFoundError(f"ModelScope 下载后未找到模型: {_local}")
        ckpt_path = _found[0]
        _p(f"[F5-TTS] 模型已下载: {os.path.basename(ckpt_path)}")

    _p(f"[F5-TTS] 设备: {device}，加载主模型（首次约需 10~30 秒）…")

    _f5_tts_model = load_model(
        model_cls=model_cls,
        model_cfg=model_arc,
        ckpt_path=ckpt_path,
        mel_spec_type=vocoder_name,
        device=device,
    )

    # ── 关键修复：model.sample() 在 float16 下产生 18%+ NaN ──────────
    # F5-TTS 的 load_checkpoint 会自动将 model 转为 float16（当 compute capability >= 7 时），
    # 但 float16 推理对于 CFM (Continuous Flow Matching) 模型精度不够，
    # 导致 model.sample() 输出大量 NaN，经 vocoder 后变成全 NaN 音频。
    # 修复：加载后强制转回 float32。
    _model_dtype = next(_f5_tts_model.parameters()).dtype
    if _model_dtype == torch.float16:
        _f5_tts_model = _f5_tts_model.float()
        _p(f"[F5-TTS] 主模型已从 float16 转回 float32（修复 NaN 问题）")

    _p("[F5-TTS] 主模型加载完成，加载 vocoder…")

    # vocos 本地路径：f5_tts 包目录下的 vocos_local/charactr/vocos-mel-24khz/
    _vocos_local_path = os.path.join(_pkg_dir, "infer", "examples", "vocos_local", "charactr", "vocos-mel-24khz")

    # ── 4GB 显存优化：vocos 保持 float32 ────────────────────────────
    _f5_tts_vocoder = load_vocoder(vocoder_name=vocoder_name, is_local=True, local_path=_vocos_local_path, device=device)
    # vocos 不转 float16：vocos 的 iSTFT (逆短时傅里叶变换) 涉及复数运算，
    # float16 (ComplexHalf) 是实验性的，会导致全部输出 NaN/Inf。
    # 显存优化依赖 _VocoderOffloadProxy 在推理时 offload 到 CPU 实现。
    _p("[F5-TTS] Vocoder 加载完成！模型已就绪。")

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return _f5_tts_model, _f5_tts_vocoder


class _VocoderOffloadProxy:
    """Vocoder 代理：在非 decode 时将 vocoder 驻留 CPU，节省 GPU 显存。

    用法：在 monkey-patch infer_batch_process 时替换 vocoder 参数。
    由于 F5-TTS 内部直接调用 vocoder.decode()，代理对象需要兼容该接口。
    """

    def __init__(self, vocoder, device):
        object.__setattr__(self, "_real", vocoder)
        object.__setattr__(self, "_device", device)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __call__(self, *args, **kwargs):
        return self._real(*args, **kwargs)

    def decode(self, x):
        """将 vocoder 移到与 x 相同的 device，decode 后移回 CPU。"""
        v = self._real
        target_device = x.device
        if target_device.type == "cuda":
            v = v.to(target_device)
            torch.cuda.empty_cache()
        result = v.decode(x)
        # decode 完成后移回 CPU 释放显存
        self._real.cpu()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return result


# ── 情感预设配置 ──────────────────────────────────────────────────────────
# 每种情感对应一个文本前缀标记，注入到 gen_text 开头，引导模型风格
# 这是基于 prompt engineering 的情感控制，不需要额外模型
EMOTION_PRESETS = {
    "无（正常）":   "",
    "😊 开心":     "[开心] ",
    "😢 悲伤":     "[悲伤] ",
    "😠 愤怒":     "[愤怒] ",
    "😨 恐惧":     "[恐惧] ",
    "😲 惊讶":     "[惊讶] ",
    "😌 平静":     "[平静] ",
    "🤩 兴奋":     "[兴奋] ",
    "🥰 温柔":     "[温柔] ",
    "😏 严肃":     "[严肃] ",
}

# 各情感的 CFG strength 推荐值（情感越强烈，建议适当提高）
EMOTION_CFG_STRENGTH = {
    "无（正常）":   2.0,
    "😊 开心":     2.5,
    "😢 悲伤":     2.5,
    "😠 愤怒":     3.0,
    "😨 恐惧":     2.5,
    "😲 惊讶":     2.5,
    "😌 平静":     2.0,
    "🤩 兴奋":     3.0,
    "🥰 温柔":     2.0,
    "😏 严肃":     2.0,
}


class F5TTSEngine:
    """
    F5-TTS 声音克隆引擎。

    关键参数：
      - ref_audio:       参考音频路径（支持 .wav, .mp3, .flac）
      - ref_text:        参考音频对应的文字 transcript
      - speed:           语速倍率（默认 1.0，>1 更快，<1 更慢）
      - nfe_step:        推理步数（默认 32，越大越慢但可能更准确）
      - cf_strength:     CFG 强度（默认 2.0，情感模式下自动调整）
      - emotion:         情感预设名称，见 EMOTION_PRESETS（默认无）
      - emotion_ref_audio: 情感参考音频路径（可选，提供带目标情感的音频
                           以替换主参考音频进行风格引导）
    """

    def __init__(
        self,
        ref_audio: str | None = None,
        ref_text: str | None = None,
        speed: float = 1.0,
        nfe_step: int = 32,
        cf_strength: float = 2.0,
        emotion: str = "无（正常）",
        emotion_ref_audio: str | None = None,
    ):
        if not _check_f5_tts():
            raise ImportError(
                "f5-tts 未安装，请运行：\n"
                "  pip install f5-tts --user -i https://pypi.tuna.tsinghua.edu.cn/simple"
            )

        self.ref_audio = ref_audio
        self.ref_text = ref_text or ""
        self.speed = speed
        self.nfe_step = nfe_step
        self.cf_strength = cf_strength
        self.emotion = emotion
        self.emotion_ref_audio = emotion_ref_audio

        # 播放状态
        self._speaking = False
        self._busy = False
        self._stop_flag = False
        self._lock = threading.Lock()

        # 参考音频预处理缓存（主 ref + 情感 ref 各一份）
        self._ref_audio_processed: str | None = None
        self._emotion_ref_processed: str | None = None

        if ref_audio and ref_text:
            self._preprocess_ref()

    # ------------------------------------------------------------------
    # 参考音频预处理
    # ------------------------------------------------------------------

    def _preprocess_ref(self):
        """预处理主参考音频（F5-TTS 需要标准化格式）"""
        import f5_tts.infer.utils_infer  # 触发模块初始化

        from f5_tts.infer.utils_infer import preprocess_ref_audio_text

        print(f"[F5-TTS] 预处理参考音频: {os.path.basename(self.ref_audio)}")

        ref_audio_proc, ref_text_out = preprocess_ref_audio_text(
            self.ref_audio,
            self.ref_text,
            show_info=lambda x: print(f"  {x}"),
        )

        self._ref_audio_processed = self._normalize_ref_audio(ref_audio_proc)
        self.ref_text = ref_text_out   # preprocess 会自动补句末标点
        print(f"[F5-TTS] 参考音频预处理完成: {ref_audio_proc}")

        # 如果有情感参考音频，同步预处理
        if self.emotion_ref_audio:
            self._preprocess_emotion_ref()

    def _preprocess_emotion_ref(self):
        """预处理情感参考音频（只用于风格引导，不需要对应文字）"""
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        try:
            print(f"[F5-TTS] 预处理情感参考音频: {os.path.basename(self.emotion_ref_audio)}")
            # 情感参考音频文字用空字符串，仅用其音频特征
            emo_proc, _ = preprocess_ref_audio_text(
                self.emotion_ref_audio, "",
                show_info=lambda x: print(f"  {x}"),
            )
            self._emotion_ref_processed = self._normalize_ref_audio(emo_proc)
            print(f"[F5-TTS] 情感参考音频预处理完成")
        except Exception as e:
            print(f"[F5-TTS] 情感参考音频预处理失败，忽略: {e}")
            self._emotion_ref_processed = None

    def _normalize_ref_audio(self, audio_path: str) -> str:
        """音量归一化参考音频，确保推理稳定性，返回处理后路径"""
        try:
            import torchaudio as _ta
            _wav, _sr = _ta.load(audio_path)
            if _sr != 24000:
                _resampler = _ta.transforms.Resample(_sr, 24000)
                _wav = _resampler(_wav)
            if _wav.shape[0] > 1:
                _wav = _wav.mean(dim=0, keepdim=True)
            _peak = _wav.abs().max().item()
            if _peak > 0 and _peak < 0.15:
                _scale = 0.7 / _peak
                _wav = (_wav * _scale).clamp(-0.95, 0.95)
                _ta.save(audio_path, _wav, 24000)
                print(f"[F5-TTS] 参考音频音量过低（peak={_peak:.4f}），已归一化到 0.7")
            elif _peak > 0.95:
                _wav = (_wav * (0.9 / _peak)).clamp(-0.95, 0.95)
                _ta.save(audio_path, _wav, 24000)
                print(f"[F5-TTS] 参考音频音量过大（peak={_peak:.4f}），已压限到 0.9")
        except Exception as _e:
            print(f"[F5-TTS] 参考音频归一化跳过: {_e}")
        return audio_path

    # ------------------------------------------------------------------
    # 核心推理
    # ------------------------------------------------------------------

    def _generate_audio(self, text: str, progress_callback=None) -> np.ndarray:
        """调用 F5-TTS 推理，返回 numpy 音频数组（24000Hz 单通道）"""
        from f5_tts.infer import utils_infer as _ui

        # ── 4GB 显存优化：推理前清理缓存 ─────────────────────────────
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

        model, vocoder = _load_f5_tts(progress_callback=progress_callback)

        if not self._ref_audio_processed:
            raise ValueError(
                "F5-TTS 需要参考音频！请在初始化时传入 ref_audio 和 ref_text 参数。"
            )

        # ── 情感前缀注入 ─────────────────────────────────────────────
        # 在 gen_text 前插入情感标记词，引导模型风格
        emotion_prefix = EMOTION_PRESETS.get(self.emotion, "")
        gen_text = (emotion_prefix + text) if emotion_prefix else text

        # 情感模式下动态调整 CFG strength（增强情感表现力）
        cfg_strength = EMOTION_CFG_STRENGTH.get(self.emotion, self.cf_strength)
        # 用户自定义 cf_strength 覆盖预设（如果用户明确设置了非默认值）
        if self.cf_strength != 2.0:
            cfg_strength = self.cf_strength

        # ── 情感参考音频选择 ─────────────────────────────────────────
        # 若有情感参考音频，用它替代主参考音频进行推理（只影响本次推理）
        if self.emotion_ref_audio and self._emotion_ref_processed:
            active_ref = self._emotion_ref_processed
            active_ref_text = ""   # 情感参考音频无文字，置空
            print(f"[F5-TTS] 使用情感参考音频：{os.path.basename(self.emotion_ref_audio)}")
        else:
            active_ref = self._ref_audio_processed
            active_ref_text = self.ref_text

        print(f"[F5-TTS] 合成中: 情感=[{self.emotion}] cfg={cfg_strength:.1f} 文本={gen_text[:50]}{'...' if len(gen_text) > 50 else ''}")

        # ── 4GB 显存优化：monkey-patch infer_batch_process 实现 vocoder offload ──
        # 原始流程：model.sample() + vocoder.decode() 都在 GPU 上，4GB 显存不够
        # 优化流程：推理 mel 时 vocoder 在 CPU，decode 时移回 GPU
        #
        # infer_batch_process 签名（位置参数 + 关键字参数）：
        #   ref_audio, ref_text, gen_text_batches, model_obj, vocoder, ...
        # infer_process 调用方式：全部用关键字参数传入（vocoder=vocoder）
        # 所以 vocoder 在 kwargs 里，不在 args 位置上
        _orig_infer_batch = _ui.infer_batch_process

        def _patched_infer_batch(*args, **kwargs):
            vocoder_arg = kwargs.get("vocoder")
            # 兜底：万一某些版本通过位置参数传入
            if vocoder_arg is None and len(args) > 4:
                vocoder_arg = args[4]

            device_arg = kwargs.get("device", _ui.device)
            # _ui.device 是字符串 "cuda"/"cpu"，统一包装为 torch.device
            if isinstance(device_arg, str):
                device_arg = torch.device(device_arg)

            if torch.cuda.is_available() and vocoder_arg is not None:
                proxy = _VocoderOffloadProxy(vocoder_arg, device_arg)
                # 只替换 kwargs 中的 vocoder（infer_process 通过关键字参数传入）
                # 如果 args[4] 也恰好是 vocoder，必须从 args 中移除，否则会
                #   "got multiple values for argument 'vocoder'"
                if "vocoder" in kwargs or len(args) > 4:
                    kwargs["vocoder"] = proxy
                    # 若 args 长度 >= 5，截断掉位置上的 vocoder（由 kwargs 接管）
                    if len(args) > 4:
                        args = args[:4]

            return _orig_infer_batch(*args, **kwargs)

        _ui.infer_batch_process = _patched_infer_batch

        try:
            # 调用推理（返回 3 值: wave, sr, spectrogram）
            result = _ui.infer_process(
                ref_audio=active_ref,
                ref_text=active_ref_text,
                gen_text=gen_text,
                model_obj=model,
                vocoder=vocoder,
                speed=self.speed,
                nfe_step=self.nfe_step,
                cfg_strength=cfg_strength,
            )
        finally:
            # 恢复原始函数
            _ui.infer_batch_process = _orig_infer_batch

        if result is None:
            raise RuntimeError("F5-TTS 推理失败，返回 None")

        audio, _sr, _spectrogram = result

        # ── 截掉参考音频泄漏（ref audio leakage） ───────────────────
        # F5-TTS 推理时，模型输入是 ref_text + gen_text，生成的 mel 频谱前半部分
        # 对应参考音频内容。代码用 ref_audio_len (hop_length 对齐) 跳过这部分，
        # 但由于参考音频时长与 ref_text 字数比的估算误差，截断点可能偏移，
        # 导致参考音频末尾的内容泄漏到输出开头。
        #
        # 修复：基于实际推理时使用的参考音频时长计算采样点，额外加 0.3 秒安全余量。
        try:
            _ref_wav, _ref_sr = torchaudio.load(active_ref)
            _ref_samples = _ref_wav.shape[-1]
            # 采样率统一为 24000
            if _ref_sr != 24000:
                _ref_samples = int(_ref_samples * 24000 / _ref_sr)
            # 加 0.3 秒安全余量（约 7200 采样点），确保完全切掉参考音频内容
            _trim_samples = _ref_samples + int(0.3 * 24000)
            if _trim_samples < len(audio):
                audio = audio[_trim_samples:]
                print(f"[F5-TTS] 已截掉参考音频泄漏（{_trim_samples} 采样点，约 {_trim_samples/24000:.1f} 秒）")
        except Exception as _e:
            print(f"[F5-TTS] 参考音频截断跳过: {_e}")

        # ── 推理后立即释放中间张量 ───────────────────────────────────
        del _spectrogram, result
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # ── NaN/Inf 自动修复 ────────────────────────────────────────
        # 模型推理偶尔产生数值不稳定（特别是低音量参考音频），
        # 用相邻有效值的线性插值替换 NaN/Inf，而非直接报错。
        if not np.isfinite(audio).all():
            invalid_mask = ~np.isfinite(audio)
            invalid_count = int(invalid_mask.sum())
            total_count = len(audio)
            print(f"[F5-TTS] 检测到 {invalid_count}/{total_count} 个 NaN/Inf，自动修复中…")

            if invalid_count > total_count * 0.3:
                raise ValueError(
                    f"F5-TTS 推理产生了过多无效值（{invalid_count}/{total_count}）。"
                    f"请尝试：\n"
                    f"  1. 换一段更清晰的参考音频（10~30秒，背景安静）\n"
                    f"  2. 确保参考文本与音频内容完全一致\n"
                    f"  3. 降低推理步数（nfe_step 调小，推荐 16~24）"
                )

            # 用最近邻有效值填充 NaN/Inf（向量化实现）
            audio_fixed = audio.copy()
            valid_mask = np.isfinite(audio)

            if valid_mask.any():
                # 用有效值的最近邻插值：先向前填充，再向后填充
                # 方法：构建纯有效值数组，对无效区域做线性插值
                valid_indices = np.where(valid_mask)[0]
                invalid_indices = np.where(~valid_mask)[0]

                # 批量线性插值
                left_idx = np.searchsorted(valid_indices, invalid_indices, side='right') - 1
                right_idx = left_idx + 1
                right_idx = np.clip(right_idx, 0, len(valid_indices) - 1)

                left_vals = audio[valid_indices[left_idx]]
                right_vals = audio[valid_indices[right_idx]]

                left_positions = valid_indices[left_idx]
                right_positions = valid_indices[right_idx]

                span = right_positions - left_positions
                span = np.where(span == 0, 1, span)  # 避免除零
                t = (invalid_indices - left_positions).astype(np.float64) / span

                audio_fixed[invalid_indices] = left_vals * (1 - t) + right_vals * t
            else:
                audio_fixed = np.zeros_like(audio)

            # 软限幅防止修复后出现极端值
            audio_fixed = np.clip(audio_fixed, -1.0, 1.0)
            audio = audio_fixed
            print(f"[F5-TTS] NaN/Inf 修复完成")

        return audio

    # ------------------------------------------------------------------
    # 播放控制
    # ------------------------------------------------------------------

    def speak(self, text: str, block: bool = False, progress_callback=None):
        """
        朗读文本（声音克隆自参考音频）。

        :param text:  要朗读的文本
        :param block: True = 同步阻塞；False = 后台线程播放
        """
        if not text.strip():
            return

        self.stop()

        with self._lock:
            self._speaking = False
            self._stop_flag = False

        def _run():
            try:
                audio_np = self._generate_audio(text, progress_callback=progress_callback)

                # 检查 NaN/Inf（_generate_audio 已尝试自动修复，这里做最终检查）
                if not np.isfinite(audio_np).all():
                    invalid_count = (~np.isfinite(audio_np)).sum()
                    raise ValueError(
                        f"F5-TTS 推理产生了无效音频（{invalid_count} 个 NaN/Inf 值，无法自动修复）。"
                        f"请尝试：\n"
                        f"  1. 换一段更清晰的参考音频（10~30秒，背景安静）\n"
                        f"  2. 确保参考文本与音频内容完全一致\n"
                        f"  3. 降低推理步数（nfe_step 调小，推荐 16~24）"
                    )

                # 转换为 pygame 可播放的格式
                audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)

                buf = io.BytesIO()
                sf.write(buf, audio_int16, 24000, format="WAV")
                buf.seek(0)

                pygame.mixer.music.load(buf)

                with self._lock:
                    self._speaking = True

                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if self._stop_flag:
                        pygame.mixer.music.stop()
                        break
                    pygame.time.Clock().tick(10)

                with self._lock:
                    self._speaking = False

            except Exception as e:
                sys.stderr.write(f"[F5-TTS 错误] {e}\n")
                with self._lock:
                    self._speaking = False

        if block:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        """立即停止播放"""
        with self._lock:
            if self._speaking:
                self._stop_flag = True
            pygame.mixer.music.stop()

    @property
    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking or pygame.mixer.music.get_busy()

    # ------------------------------------------------------------------
    # 文件导出
    # ------------------------------------------------------------------

    def save_to_file(self, text: str, output_path: str, progress_callback=None):
        """
        将克隆声音的合成音频保存为文件。

        :param text:        要合成的文本
        :param output_path: 输出路径（支持 .wav, .mp3, .flac）
        """
        audio_np = self._generate_audio(text, progress_callback=progress_callback)

        # 检查 NaN/Inf（_generate_audio 已尝试自动修复，这里做最终检查）
        if not np.isfinite(audio_np).all():
            raise ValueError(
                "F5-TTS 推理产生了无效音频（NaN/Inf，无法自动修复）。"
                "请尝试：1) 换一段更清晰的参考音频 2) 确保参考文本与音频内容一致 3) 降低推理步数（推荐 16~24）"
            )

        ext = os.path.splitext(output_path)[1].lower()

        if ext == ".mp3":
            # soundfile 不直接支持 mp3，用 pydub 转换
            import tempfile as _tmp
            tmp_wav = os.path.join(_tmp.gettempdir(), f"f5_tts_tmp_{os.getpid()}.wav")
            sf.write(tmp_wav, audio_np, 24000)
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_wav(tmp_wav)
            audio_seg.export(output_path, format="mp3")
            os.remove(tmp_wav)
        else:
            sf.write(output_path, audio_np, 24000)

        print(f"[F5-TTS] 已保存: {output_path}")
