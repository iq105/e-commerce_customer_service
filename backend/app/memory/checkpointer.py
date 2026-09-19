import os
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_URL = os.getenv("DB_URL")
_conn = Connection.connect(DB_URL, autocommit=True)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()