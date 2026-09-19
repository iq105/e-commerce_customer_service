import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from backend.app.tools.order import order_tools

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

model = ChatOpenAI(model=os.getenv("MODEL_NAME"), base_url=os.getenv("OPENAI_BASE_URL"),
                   api_key=os.getenv("OPENAI_API_KEY"), max_tokens=4096, max_retries=3,
                   openai_proxy=os.getenv("OPENAI_PROXY") or None)

model_with_tools = model.bind_tools(order_tools)