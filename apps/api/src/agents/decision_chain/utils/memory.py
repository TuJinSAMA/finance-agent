import sqlite3
from pathlib import Path
from typing import List, Tuple

from rank_bm25 import BM25Okapi


class FinancialSituationMemory:
    """BM25-based memory for storing and retrieving financial situations, persisted in SQLite."""

    def __init__(self, name: str, db_dir: str | None = None):
        self.name = name
        self.documents: List[str] = []
        self.recommendations: List[str] = []
        self.bm25: BM25Okapi | None = None

        if db_dir:
            db_path = Path(db_dir)
            db_path.mkdir(parents=True, exist_ok=True)
            self._db_path = db_path / f"{name}.db"
            self._load_from_db()
        else:
            self._db_path = None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, situation TEXT, recommendation TEXT)"
        )
        conn.commit()
        return conn

    def _load_from_db(self):
        if not self._db_path:
            return
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT situation, recommendation FROM memories").fetchall()
            self.documents = [r[0] for r in rows]
            self.recommendations = [r[1] for r in rows]
            self._rebuild_index()
        finally:
            conn.close()

    def _tokenize(self, text: str) -> List[str]:
        import re
        return re.findall(r"\b\w+\b", text.lower())

    def _rebuild_index(self):
        if self.documents:
            tokenized_docs = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_docs)
        else:
            self.bm25 = None

    def add_situations(self, situations_and_advice: List[Tuple[str, str]]):
        for situation, recommendation in situations_and_advice:
            self.documents.append(situation)
            self.recommendations.append(recommendation)
        self._rebuild_index()
        if self._db_path:
            self._save_to_db(situations_and_advice)

    def _save_to_db(self, situations_and_advice: List[Tuple[str, str]]):
        conn = self._get_conn()
        try:
            conn.executemany(
                "INSERT INTO memories (situation, recommendation) VALUES (?, ?)",
                situations_and_advice,
            )
            conn.commit()
        finally:
            conn.close()

    def get_memories(self, current_situation: str, n_matches: int = 2) -> List[dict]:
        if not self.documents or self.bm25 is None:
            return []
        query_tokens = self._tokenize(current_situation)
        scores = self.bm25.get_scores(query_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_matches]
        max_score = max(scores) if max(scores) > 0 else 1
        results = []
        for idx in top_indices:
            normalized_score = scores[idx] / max_score if max_score > 0 else 0
            results.append({
                "matched_situation": self.documents[idx],
                "recommendation": self.recommendations[idx],
                "similarity_score": normalized_score,
            })
        return results

    def clear(self):
        self.documents = []
        self.recommendations = []
        self.bm25 = None
        if self._db_path:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM memories")
                conn.commit()
            finally:
                conn.close()