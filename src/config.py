import os
from dotenv import load_dotenv

load_dotenv()

# Default model
# User requested "flash-2.5", assuming they mean gemini-1.5-flash or similar high-speed model.
# We will use gemini-1.5-flash for speed and higher rate limits.
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gemini-2.5-flash")

def get_model_name():
    return DEFAULT_MODEL
