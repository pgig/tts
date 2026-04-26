"""
tts_cli.py - 文本转语音命令行工具（Edge TTS / F5-TTS / pyttsx3 三引擎）

用法示例：
    # 直接朗读（Edge TTS，神经网络音色）
    python tts_cli.py -t "你好，世界"

    # 从 PDF 导入并朗读
    python tts_cli.py -f input.pdf

    # F5-TTS 声音克隆（需提供参考音频和文本）
    python tts_cli.py --engine f5-tts -t "你好" \
        --ref-audio my_voice.wav --ref-text "这是我的参考音频内容。"

    # F5-TTS 指定语速和推理步数
    python tts_cli.py --engine f5-tts -t "快速朗读" \
        --ref-audio my_voice.wav --ref-text "这是参考。" --speed 1.5 --nfe 48

    # 列出所有可用音色（Edge TTS）
    python tts_cli.py --list-voices --engine edge-tts

    # 保存为音频文件
    python tts_cli.py -t "保存测试" -o output.mp3 --engine edge-tts
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# 优先 Edge TTS
USE_EDGE_TTS = True
try:
    from edge_tts_engine import EdgeTTSEngine as TTSEngine
    _default_engine = "edge-tts"
except ImportError:
    USE_EDGE_TTS = False
    try:
        from f5_tts_engine import F5TTSEngine as TTSEngine
        _default_engine = "f5-tts"
    except ImportError:
        from tts_engine import TTSEngine
        _default_engine = "pyttsx3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tts_cli",
        description=f"文本转语音工具（默认 {_default_engine}）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engine", choices=["edge-tts", "f5-tts", "pyttsx3"], default=_default_engine,
        help="指定 TTS 引擎（默认自动选择）"
    )

    # 输入源（互斥）
    src = parser.add_mutually_exclusive_group()
    src.add_argument("-t", "--text", metavar="TEXT", help="直接传入要朗读的文本")
    src.add_argument(
        "-f", "--file", metavar="FILE",
        help="从文件读取（自动识别 .pdf / .txt）",
    )

    # 参数（Edge TTS）
    parser.add_argument(
        "-r", "--rate", type=int, default=0,
        help="语速（Edge TTS: -100~+100，0=正常；pyttsx3: 词/分钟）",
    )
    parser.add_argument(
        "-p", "--pitch", type=int, default=0,
        help="音调（Edge TTS 专属，-50~+50 Hz，默认 0）",
    )
    parser.add_argument(
        "-v", "--volume", type=float, default=1.0,
        help="音量（Edge TTS: 0~2.0，pyttsx3: 0~1.0）",
    )
    parser.add_argument(
        "--voice", metavar="NAME",
        help="指定音色名称（如 zh-CN-XiaoxiaoNeural）",
    )
    parser.add_argument(
        "--lang", default="zh",
        help="列出音色时的语言过滤（如 zh / en / all，默认 zh）",
    )

    # 输出
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="保存为音频文件而非播放（.mp3 / .wav）",
    )

    # 信息
    parser.add_argument(
        "--list-voices", action="store_true",
        help="列出所有可用音色并退出",
    )
    parser.add_argument(
        "--platform", action="store_true",
        help="显示当前平台与后端信息",
    )

    # F5-TTS 专属参数
    parser.add_argument(
        "--ref-audio", metavar="FILE",
        help="F5-TTS：参考音频文件路径（用于声音克隆）",
    )
    parser.add_argument(
        "--ref-text", metavar="TEXT",
        help="F5-TTS：参考音频对应的文字 transcript（必须与音频内容完全一致）",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="F5-TTS：语速倍率（0.5~2.0，默认 1.0）",
    )
    parser.add_argument(
        "--nfe", type=int, default=32,
        help="F5-TTS：推理步数（16~64，默认 32，越大越慢但可能更准确）",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # 动态切换引擎
    if args.engine == "edge-tts":
        try:
            from edge_tts_engine import EdgeTTSEngine
            engine_cls = EdgeTTSEngine
        except ImportError:
            print("错误：edge-tts 未安装。执行：pip install edge-tts", file=sys.stderr)
            sys.exit(1)
    elif args.engine == "f5-tts":
        try:
            from f5_tts_engine import F5TTSEngine
            engine_cls = F5TTSEngine
        except ImportError as e:
            print(f"错误：f5-tts 未安装。{e}", file=sys.stderr)
            print("执行：pip install f5-tts imageio-ffmpeg", file=sys.stderr)
            sys.exit(1)
    else:
        from tts_engine import TTSEngine
        engine_cls = TTSEngine

    # F5-TTS 需要参考音频
    if args.engine == "f5-tts":
        if not args.ref_audio:
            print("错误：F5-TTS 需要 --ref-audio 参数指定参考音频文件。", file=sys.stderr)
            sys.exit(1)
        if not args.ref_text:
            print("错误：F5-TTS 需要 --ref-text 参数指定参考音频的文字 transcript。", file=sys.stderr)
            sys.exit(1)
        engine = engine_cls(
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            speed=args.speed,
            nfe_step=args.nfe,
        )
    else:
        engine = engine_cls()

    # ── 信息查询 ───────────────────────────────────────────────
    if args.platform:
        info = engine.platform_info()
        print(f"平台：{info['platform']}")
        print(f"后端：{info['backend']}")
        print(f"需要网络：{info.get('net_required', False)}")
        sys.exit(0)

    if args.list_voices:
        if args.engine == "f5-tts":
            print("F5-TTS 是声音克隆引擎，不支持 list_voices。")
            print("请提供 --ref-audio 和 --ref-text 参数来指定要克隆的声音。")
        else:
            lang = None if args.lang == "all" else args.lang
            voices = engine.list_voices(lang=lang)
            if not voices:
                print("未检测到可用音色。")
            else:
                print(f"{'#':<4} {'音色名称':<45} {'性别':<8} {'语言'}")
                print("-" * 80)
                for i, v in enumerate(voices):
                    print(f"{i:<4} {v.get('short_name',v.get('name','')):<45} "
                          f"{v.get('gender','?'):<8} {v.get('locale','')}")
        sys.exit(0)

    # ── 获取文本 ───────────────────────────────────────────────
    text = ""
    if args.text:
        text = args.text
    elif args.file:
        try:
            ext = args.file.lower().rsplit(".", 1)[-1]
            if ext == "pdf":
                from tts_engine import TTSEngine as _PdfEngine
                backend = _PdfEngine.pdf_backend_name()
                if backend is None:
                    print(
                        "错误：PDF 解析需要安装 PyMuPDF 或 PyPDF2：\n"
                        "  pip install pymupdf    # 推荐，速度快",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                text = _PdfEngine.read_pdf(args.file)
            else:
                with open(args.file, "r", encoding="utf-8") as f:
                    text = f.read()
        except FileNotFoundError:
            print(f"错误：找不到文件 '{args.file}'", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"错误：读取文件失败 - {e}", file=sys.stderr)
            sys.exit(1)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(0)

    if not text.strip():
        print("错误：输入文本为空。", file=sys.stderr)
        sys.exit(1)

    # ── 设置参数 ───────────────────────────────────────────────
    if args.engine == "f5-tts":
        # F5-TTS 参数已在 engine 初始化时设置，此处可覆盖
        engine.speed = args.speed
        engine.nfe_step = args.nfe
    else:
        engine.rate = args.rate
        engine.volume = max(0.0, min(2.0 if args.engine == "edge-tts" else 1.0, args.volume))
        if hasattr(engine, 'pitch') and args.pitch:
            engine.pitch = args.pitch
        if args.voice:
            engine.voice = args.voice

    # ── 执行 ───────────────────────────────────────────────────
    if args.output:
        print(f"正在保存音频到 '{args.output}'…")
        engine.save_to_file(text, args.output)
        print("保存完成。")
    else:
        preview = text[:60].replace("\n", " ")
        if len(text) > 60:
            preview += "…"
        print(f"正在朗读：{preview}")
        engine.speak(text, block=True)
        print("朗读完毕。")


if __name__ == "__main__":
    main()
