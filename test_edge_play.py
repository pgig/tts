import sys, tempfile, os, subprocess, asyncio, edge_tts
sys.stdout.reconfigure(encoding='utf-8')

async def synth(text):
    c = edge_tts.Communicate(text, 'zh-CN-XiaoxiaoNeural')
    buf = bytearray()
    async for chunk in c.stream():
        if chunk['type'] == 'audio':
            buf.extend(chunk['data'])
    return bytes(buf)

text = 'GUI播放测试，这是一段中文朗读文本'
print('合成中...')
mp3 = asyncio.run(synth(text))
print('合成字节数:', len(mp3))

# 保存到确定路径（桌面）
out_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'test_tts.mp3')
with open(out_path, 'wb') as f:
    f.write(mp3)
print('文件路径:', out_path)
print('文件大小:', os.path.getsize(out_path), 'bytes')

# 用 cmd /c start 打开（最可靠）
print('用音乐播放器打开...')
r = subprocess.run(
    ['cmd', '/c', 'start', '', out_path],
    capture_output=True, text=True
)
print('返回码:', r.returncode)
if r.stderr:
    print('stderr:', r.stderr[:300])
print('测试完成')
