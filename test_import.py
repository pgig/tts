import sys, os
sys.path.insert(0, os.path.dirname(__file__))
print("sys.path[0]:", sys.path[0])
print("cwd:", os.getcwd())
print("edge_tts exists:", os.path.exists(os.path.join(sys.path[0], "edge_tts_engine.py")))
try:
    from edge_tts_engine import EdgeTTSEngine as TTSEngine
    print("Import OK")
except ImportError as e:
    print("Import FAILED:", e)
