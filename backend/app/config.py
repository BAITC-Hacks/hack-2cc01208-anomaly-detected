import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4.1-mini")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

DATA_PATH = (PROJECT_DIR / os.environ.get("DATA_PATH", "../data/hackathon-dataset-anonymized.jsonl")).resolve()

MAX_CARDS = 3
