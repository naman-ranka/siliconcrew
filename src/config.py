from dotenv import load_dotenv

from src.model_catalog import get_default_model_name

load_dotenv()

# Default model. Provider is inferred from model name prefix.
# Supported families:
# - gemini-*
# - gpt-* / chatgpt-* / o1* / o3* / o4*
# - claude-*
DEFAULT_MODEL = get_default_model_name()


def get_model_name():
    return DEFAULT_MODEL
