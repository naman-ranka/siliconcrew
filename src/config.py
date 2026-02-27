import os
from dotenv import load_dotenv

load_dotenv()

# Default model. Provider is inferred from model name prefix.
# Supported families:
# - gemini-*
# - gpt-* / chatgpt-* / o1* / o3* / o4*
# - claude-*
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "gemini-3-flash-preview")

def get_model_name():
    return DEFAULT_MODEL
