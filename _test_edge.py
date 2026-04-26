import sys
sys.stdout.reconfigure(encoding='utf-8')
from edge_tts_engine import EdgeTTSEngine
import os

# 列出中文音色
voices = EdgeTTSEngine.list_voices('zh')
print('中文音色数量:', len(voices))
for v in voices:
    tag = v.get('friendly', '')
    print(f"  {v['short_name']}  {v['gender']}  {tag}")

# 合成测试
print()
e = EdgeTTSEngine()
print('Voice:', e.voice)
print('Rate:', e.rate, 'Pitch:', e.pitch, 'Volume:', e.volume)

print('Synthesizing test...')
e.save_to_file('Edge TTS 测试成功', 'tts/_edge_test.mp3')
size = os.path.getsize('tts/_edge_test.mp3')
print(f'MP3 size: {size} bytes - OK')
os.remove('tts/_edge_test.mp3')
print('All done.')
