import sys, traceback
sys.path.insert(0, r'C:\Users\Faisal\Downloads\Virtual Ai Assistant')
from core.tasks.brain import ask
try:
    r = ask('You are a test. Reply with exactly one word: OK', [], [])
    print('BRAIN_OK: ' + str(r)[:400])
except Exception as e:
    print('BRAIN_FAIL: ' + type(e).__name__ + ': ' + str(e)[:600])
    traceback.print_exc()
