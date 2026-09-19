import os
from pathlib import Path

from dotenv import load_dotenv
from langgraph.store.postgres import PostgresStore
from psycopg import Connection

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_URL = os.getenv("DB_URL")

_conn = Connection.connect(DB_URL, autocommit=True)
store = PostgresStore(_conn)
store.setup()