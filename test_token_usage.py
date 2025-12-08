import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

load_dotenv()

from src.config import DEFAULT_MODEL

# Use the model from config
model_name = DEFAULT_MODEL
print(f"Testing model: {model_name}")

try:
    llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=os.environ.get("GOOGLE_API_KEY"))
    msg = llm.invoke([HumanMessage(content="Hello, say 'test'.")])
    
    print("Response Content:", msg.content)
    import json
    print("Usage Metadata:", json.dumps(msg.usage_metadata, indent=2))
    # print("Response Metadata Keys:", msg.response_metadata.keys())
    print("Full Response Metadata:", msg.response_metadata)
    # Check if it's in the raw generation info
    if 'generation_info' in msg.response_metadata:
        print("Generation Info:", msg.response_metadata['generation_info'])
    
except Exception as e:
    print(f"Error: {e}")
