"""Text-only keyword baseline with local and hosted storage configuration.

Run setup_local_key.py first, then:
python -m uvicorn competition_app_secure:app --host 127.0.0.1 --port 8000
CHRONOMEM_DB_PATH can point to a persistent disk on a hosting service.
This baseline has not passed official Smoke or Full evaluation.
"""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, StringConstraints


load_dotenv(Path(__file__).with_name(".env"), override=False)
API_KEY = os.environ.get("CHRONOMEM_API_KEY", "")
if not API_KEY.strip():
    raise RuntimeError("CHRONOMEM_API_KEY is missing. Run setup_local_key.py first.")

VERSION = os.environ.get("CHRONOMEM_VERSION", "0.2.0-keyword")
app = FastAPI(title="ChronoMem - Text Keyword Baseline (API Key)", version=VERSION)
DB_PATH = Path(os.environ.get("CHRONOMEM_DB_PATH", "chronomem_contract.db"))
if not DB_PATH.is_absolute():
    DB_PATH = Path(__file__).resolve().parent / DB_PATH
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
NonBlank = Annotated[str, StringConstraints(pattern=r"\S")]
key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def require_api_key(provided: str | None = Depends(key_header)):
    if provided is None or not secrets.compare_digest(
        provided.encode("utf-8"), API_KEY.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def connect():
    return sqlite3.connect(DB_PATH, timeout=30)


with closing(connect()) as conn:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS writes (
            user_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            PRIMARY KEY (user_id, request_id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            source_timestamp INTEGER
        );
        CREATE INDEX IF NOT EXISTS messages_by_user ON messages(user_id);
    """)
    conn.commit()


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: NonBlank
    timestamp: int | None = None


class AddInput(BaseModel):
    request_id: NonBlank
    messages: list[Message] = Field(min_length=1)
    user_id: NonBlank
    session_id: NonBlank


class SearchInput(BaseModel):
    query: NonBlank
    user_id: NonBlank
    top_k: int = Field(ge=1)
    options: list[str] | None = None


@app.get("/health")
def health():
    with closing(connect()) as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "version": VERSION, "storage": "sqlite"}


@app.post("/add", status_code=200, dependencies=[Depends(require_api_key)])
def add_memory(item: AddInput):
    payload = json.dumps(item.model_dump(), sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with closing(connect()) as conn:
        # One transaction makes retries safe, including concurrent retries.
        conn.execute("BEGIN IMMEDIATE")
        with conn:
            previous = conn.execute(
                "SELECT payload_hash FROM writes WHERE user_id=? AND request_id=?",
                (item.user_id, item.request_id),
            ).fetchone()
            if previous is not None and previous[0] != digest:
                raise HTTPException(
                    status_code=400,
                    detail="request_id was already used with a different payload",
                )
            if previous is None:
                conn.executemany(
                    "INSERT INTO messages "
                    "(user_id, session_id, request_id, position, role, content, source_timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (item.user_id, item.session_id, item.request_id, index,
                         message.role, message.content, message.timestamp)
                        for index, message in enumerate(item.messages)
                    ],
                )
                conn.execute(
                    "INSERT INTO writes VALUES (?, ?, ?)",
                    (item.user_id, item.request_id, digest),
                )
    return {
        "success": True,
        "request_id": item.request_id,
        "user_id": item.user_id,
        "session_id": item.session_id,
    }


@app.post("/search", dependencies=[Depends(require_api_key)])
def search_memories(item: SearchInput):
    # This lesson uses literal phrase matching, not semantic retrieval.
    keyword = item.query.strip().casefold()
    data = []
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, content FROM messages WHERE user_id=? ORDER BY id",
            (item.user_id,),
        )
        for memory_id, content in rows:
            if keyword in content.casefold():
                data.append({"id": f"mem_{memory_id}", "content": content})
                if len(data) >= item.top_k:
                    break
    # All phrase matches tie in this baseline; insertion order breaks ties.
    return {"data": data}
