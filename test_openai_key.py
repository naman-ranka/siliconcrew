"""
OpenAI API key diagnostics.
Checks key validity, accessible models, and infers quota/tier status.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY not set in .env")
    sys.exit(1)

try:
    from openai import OpenAI, AuthenticationError, PermissionDeniedError
    import openai
except ImportError:
    print("ERROR: openai package not installed. Run: pip install openai")
    sys.exit(1)

client = OpenAI(api_key=api_key)

# ---------------------------------------------------------------------------
# 1. Key validity — list models (cheapest possible call, no tokens used)
# ---------------------------------------------------------------------------
print("=" * 55)
print("1. Checking key validity via GET /v1/models ...")
try:
    models_page = client.models.list()
    model_ids = sorted(m.id for m in models_page.data)
    print(f"   Key is VALID — {len(model_ids)} models accessible")
except AuthenticationError:
    print("   Key is INVALID or revoked (401 Unauthorized)")
    sys.exit(1)
except Exception as e:
    print(f"   Unexpected error: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Model access — which of our target models are listed
# ---------------------------------------------------------------------------
TARGET_MODELS = ["gpt-5.4", "gpt-5.4-mini", "gpt-5-mini", "gpt-5.3-codex", "o3"]
print("\n2. Checking model access (from /v1/models list) ...")
for m in TARGET_MODELS:
    found = m in model_ids
    status = "available" if found else "NOT in your plan / not yet released"
    print(f"   {m:<20} {status}")

# ---------------------------------------------------------------------------
# 3. Quota check — attempt a real call on cheapest available model
# ---------------------------------------------------------------------------
print("\n3. Quota check — attempting inference on cheapest model ...")

# Pick the cheapest accessible model to minimize cost
cheap_candidates = ["gpt-5-mini", "gpt-5.4-mini", "gpt-5.4"]
test_model = next((m for m in cheap_candidates if m in model_ids), cheap_candidates[0])

print(f"   Using model: {test_model}")
try:
    response = client.responses.create(model=test_model, input="Say: OK")
    print(f"   Quota OK — response: {response.output_text.strip()!r}")
except openai.RateLimitError as e:
    msg = str(e)
    if "insufficient_quota" in msg:
        print("   QUOTA EXHAUSTED — account has no remaining credits.")
        print("   Fix: platform.openai.com > Billing > Add credits")
    else:
        print(f"   Rate limited (but credits exist): {e}")
except openai.PermissionDeniedError as e:
    print(f"   Permission denied — model may require a higher tier: {e}")
except Exception as e:
    print(f"   Error: {e}")

print("=" * 55)
print("Dashboard: platform.openai.com/usage")
