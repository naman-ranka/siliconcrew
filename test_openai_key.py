"""Quick smoke test: verifies OPENAI_API_KEY is valid and checks model accessibility."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY not set in .env")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

client = OpenAI(api_key=api_key)

MODELS = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini"]

any_passed = False
for model in MODELS:
    print(f"Testing {model}...", end=" ", flush=True)
    try:
        response = client.responses.create(
            model=model,
            input="Reply with exactly: OK",
        )
        reply = response.output_text.strip()
        print(f"OK  (response: {reply!r})")
        any_passed = True
    except Exception as e:
        code = getattr(e, "code", None) or type(e).__name__
        print(f"FAILED [{code}] {e}")

sys.exit(0 if any_passed else 1)
