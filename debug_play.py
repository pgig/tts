import sys, time, asyncio, edge_tts, tempfile, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')

async def synth(text):
    c = edge_tts.Communicate(text, 'zh-CN-XiaoxiaoNeural')
    buf = bytearray()
    async for chunk in c.stream():
        if chunk['type'] == 'audio':
            buf.extend(chunk['data'])
    return bytes(buf)

text = 'PowerShell Start-Process 等待测试'
mp3 = asyncio.run(synth(text))
print('bytes:', len(mp3))

with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
    tmp.write(mp3)
    path = tmp.name
print('Playing...')
t0 = time.time()
proc = subprocess.Popen(
    ['powershell', '-WindowStyle', 'Hidden', '-Command',
     f"Start-Process -FilePath '{path}' -Wait"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
wait_time = proc.wait()
print('PowerShell -Wait returned after', round(time.time()-t0, 2), 's')
os.remove(path)
