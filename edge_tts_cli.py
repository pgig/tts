"""
edge_tts_cli.py - Edge TTS 命令行工具

Usage:
    python edge_tts_cli.py -t "你好"                          # 朗读文本
    python edge_tts_cli.py -f input.txt                       # 朗读文件
    python edge_tts_cli.py -f input.pdf                       # PDF 导入朗读
    python edge_tts_cli.py -t "hello" -o output.mp3            # 保存为 MP3
    python edge_tts_cli.py --list-voices                      # 列出所有音色
    python edge_tts_cli.py --list-voices zh                   # 列出中文音色
    python edge_tts_cli.py -t "hi" -v zh-CN-YunxiNeural       # 指定音色
    python edge_tts_cli.py -t "快速" -r 50 -p 10              # 语速+50，音调+10
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from edge_tts_engine import EdgeTTSEngine


def main():
    parser = argparse.ArgumentParser(
        description="Edge TTS 命令行工具 - 微软神经网络语音合成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--text", help="要朗读的文本（直接指定）")
    group.add_argument("-f", "--file", help="要朗读的文件（.txt / .pdf）")

    parser.add_argument("-o", "--output", help="保存为音频文件（.mp3）")
    parser.add_argument("-v", "--voice",
                        default="zh-CN-XiaoxiaoNeural",
                        help="音色 ShortName（默认：zh-CN-XiaoxiaoNeural）")
    parser.add_argument("-r", "--rate", type=int, default=0,
                        help="语速：-50 ~ +100（默认 0）")
    parser.add_argument("-p", "--pitch", type=int, default=0,
                        help="音调：-50 ~ +50 Hz（默认 0）")
    parser.add_argument("--vol", type=float, default=1.0,
                        help="音量：0.0 ~ 2.0（默认 1.0）")
    parser.add_argument("--list-voices", nargs="?", const="all",
                        help="列出音色（可选：zh / en / all）")

    args = parser.parse_args()

    # 列出音色
    if args.list_voices is not None:
        lang = None if args.list_voices == "all" else args.list_voices
        voices = EdgeTTSEngine.list_voices(lang or "zh")
        print(f"\n{'ShortName':<35} {'Gender':<8} Name")
        print("-" * 80)
        for v in voices:
            name = v["name"]
            # 去掉冗余前缀
            if "Microsoft Server Speech" in name:
                name = name.split("(")[-1].rstrip(")")
            print(f"{v['short_name']:<35} {v['gender']:<8} {name}")
        print(f"\n共 {len(voices)} 个音色")
        return

    # 读取文本
    if args.file:
        path = os.path.abspath(args.file)
        if not os.path.exists(path):
            print(f"文件不存在：{path}", file=sys.stderr)
            sys.exit(1)
        ext = path.lower().rsplit(".", 1)[-1]
        if ext == "pdf":
            text = EdgeTTSEngine.read_pdf(path)
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            print(f"[PDF] 提取到 {len(text)} 字")
        else:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            print(f"[TXT] 读取 {len(text)} 字")
    else:
        text = args.text

    if not text.strip():
        print("文本为空", file=sys.stderr)
        sys.exit(1)

    # 初始化引擎
    engine = EdgeTTSEngine(
        voice=args.voice,
        rate=args.rate,
        pitch=args.pitch,
        volume=args.vol,
    )

    print(f"音色：{args.voice}  语速：{args.rate:+d}  音调：{args.pitch:+d}Hz  音量：{int(args.vol*100)}%")
    print(f"字符数：{len(text)}")

    if args.output:
        output_path = os.path.abspath(args.output)
        print(f"正在合成 → {output_path} ...")
        engine.save_to_file(text, output_path)
        print(f"完成：{output_path}")
    else:
        print("正在合成并播放...")
        engine.speak(text, block=True)
        print("播放完毕。")


if __name__ == "__main__":
    main()
