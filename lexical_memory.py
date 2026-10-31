"""A persistent, user-scoped BM25 baseline; no learned models or final answers."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import heapq
import math
import re
import unicodedata


SCHEMA = """
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    part INTEGER NOT NULL,
    content TEXT NOT NULL,
    role TEXT NOT NULL,
    source_timestamp INTEGER,
    token_count INTEGER NOT NULL,
    UNIQUE(message_id, part)
);
CREATE INDEX IF NOT EXISTS retrieval_chunks_user ON retrieval_chunks(user_id);
CREATE TABLE IF NOT EXISTS retrieval_terms (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    token TEXT NOT NULL,
    df INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, token)
);
CREATE TABLE IF NOT EXISTS retrieval_postings (
    term_id INTEGER NOT NULL,
    chunk_id INTEGER NOT NULL,
    tf INTEGER NOT NULL,
    PRIMARY KEY(term_id, chunk_id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS retrieval_stats (
    user_id TEXT PRIMARY KEY,
    chunk_count INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL
);
"""

STOPWORDS = set("a an the and or of to in on at by for with from is are was were be been being do does did what which who when where how".split())
PATTERN = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def tokenize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens = []
    for match in PATTERN.finditer(text):
        term = match.group()
        if "\u3400" <= term[0] <= "\ufaff":
            tokens.extend(term)
            tokens.extend(term[i:i + 2] for i in range(len(term) - 1))
        elif term not in STOPWORDS:
            tokens.append(term)
    return tokens


def split_text(text, size=1600, overlap=200):
    for start in range(0, len(text), size - overlap):
        piece = text[start:start + size].strip()
        if piece:
            yield piece
        if start + size >= len(text):
            break


def index_message(conn, message_id, user_id, role, content, timestamp):
    for part, piece in enumerate(split_text(content)):
        counts = Counter(tokenize(piece))
        length = sum(counts.values())
        chunk_id = conn.execute(
            "INSERT INTO retrieval_chunks "
            "(user_id,message_id,part,content,role,source_timestamp,token_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, message_id, part, piece, role, timestamp, length),
        ).lastrowid
        conn.execute(
            "INSERT INTO retrieval_stats VALUES (?,?,?) ON CONFLICT(user_id) "
            "DO UPDATE SET chunk_count=chunk_count+1,total_tokens=total_tokens+excluded.total_tokens",
            (user_id, 1, length),
        )
        if not counts:
            continue
        conn.executemany(
            "INSERT INTO retrieval_terms (user_id,token) VALUES (?,?) ON CONFLICT(user_id,token) DO NOTHING",
            [(user_id, term) for term in counts],
        )
        # A single chunk can contain thousands of Chinese terms. Use small SQL batches.
        terms = list(counts)
        term_ids = {}
        for start in range(0, len(terms), 400):
            batch = terms[start:start + 400]
            marks = ",".join("?" for _ in batch)
            term_ids.update({token: term_id for term_id, token in conn.execute(
                f"SELECT id,token FROM retrieval_terms WHERE user_id=? AND token IN ({marks})",
                [user_id, *batch],
            )})
        conn.executemany("UPDATE retrieval_terms SET df=df+1 WHERE id=?", [(term_ids[t],) for t in terms])
        conn.executemany(
            "INSERT INTO retrieval_postings VALUES (?,?,?)",
            [(term_ids[t], chunk_id, counts[t]) for t in terms],
        )


def initialize_index(conn):
    conn.executescript(SCHEMA)
    conn.execute("BEGIN IMMEDIATE")
    with conn:
        pending = conn.execute(
            "SELECT m.id,m.user_id,m.role,m.content,m.source_timestamp FROM messages m "
            "WHERE NOT EXISTS (SELECT 1 FROM retrieval_chunks c WHERE c.message_id=m.id) "
            "ORDER BY m.id"
        ).fetchall()
        for row in pending:
            index_message(conn, *row)


def search(conn, user_id, query, top_k):
    query_terms = set(tokenize(query))
    if not query_terms:
        return []
    stats = conn.execute("SELECT chunk_count,total_tokens FROM retrieval_stats WHERE user_id=?", (user_id,)).fetchone()
    if not stats or stats[0] == 0:
        return []
    count, total = stats
    average = max(total / count, 1.0)
    known = []
    terms = sorted(query_terms)
    for start in range(0, len(terms), 400):
        batch = terms[start:start + 400]
        marks = ",".join("?" for _ in batch)
        known.extend(conn.execute(
            f"SELECT id,token,df FROM retrieval_terms WHERE user_id=? AND token IN ({marks})",
            [user_id, *batch],
        ).fetchall())
    # Bound query work by using the 32 most discriminative terms found in this user's index.
    known.sort(key=lambda term: (term[2], term[1]))
    scores = defaultdict(float)
    k1, b = 1.2, 0.75
    for term_id, token, df in known[:32]:
        idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
        for chunk_id, frequency, length in conn.execute(
            "SELECT p.chunk_id,p.tf,c.token_count FROM retrieval_postings p "
            "JOIN retrieval_chunks c ON c.id=p.chunk_id WHERE p.term_id=? AND c.user_id=?",
            (term_id, user_id),
        ):
            denominator = frequency + k1 * (1 - b + b * length / average)
            scores[chunk_id] += idf * frequency * (k1 + 1) / denominator
    ranked = heapq.nlargest(top_k, scores, key=lambda chunk_id: (scores[chunk_id], -chunk_id))
    records = {}
    for start in range(0, len(ranked), 400):
        batch = ranked[start:start + 400]
        marks = ",".join("?" for _ in batch)
        for row in conn.execute(
            f"SELECT id,message_id,part,content,role,source_timestamp FROM retrieval_chunks "
            f"WHERE user_id=? AND id IN ({marks})", [user_id, *batch],
        ):
            records[row[0]] = row
    data = []
    for chunk_id in ranked:
        _, message_id, part, content, role, timestamp = records[chunk_id]
        source_time = None
        if timestamp is not None:
            try:
                source_time = datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            except (OSError, OverflowError, ValueError):
                pass
        prefix = f"[{role}; source_time={source_time}]" if source_time else f"[{role}]"
        record = {"id": f"mem_{message_id}_{part}", "content": prefix + "\n" + content, "score": scores[chunk_id]}
        if source_time:
            record["created_at"] = source_time
        data.append(record)
    return data
