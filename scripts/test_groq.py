import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend").resolve()))

from main import _call_groq_llm

prompt = [
    {"role": "system", "content": "You are a knowledgeable robotics sales engineer at PIPELINE.EV. Keep answers concise (max 2 sentences), professional, and grounded."},
    {"role": "user", "content": "Can the robotics unit handle outdoor uneven terrain?"}
]

try:
    res = _call_groq_llm(prompt, max_tokens=150)
    print("GROQ RESPONSE:")
    print(res)
except Exception as e:
    print("GROQ ERROR:", e)
