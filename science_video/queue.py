"""A transactional queue suitable for one-shot daily scheduled workers."""
import sqlite3
from pathlib import Path


class TopicQueue:
    def __init__(self, path):
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY, topic TEXT NOT NULL, due TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', output TEXT, error TEXT,
            started TEXT, finished TEXT)""")
        self.db.commit()

    def add(self, topic, due):
        with self.db:
            return self.db.execute("INSERT INTO topics(topic,due) VALUES (?,?)", (topic, due)).lastrowid

    def claim(self, today):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM topics WHERE status='pending' AND due<=? ORDER BY due,id LIMIT 1", (today,)).fetchone()
            if row:
                self.db.execute("UPDATE topics SET status='running', started=datetime('now'), error=NULL WHERE id=?", (row["id"],))
            return dict(row) if row else None

    def finish(self, id, *, output=None, error=None):
        with self.db:
            self.db.execute("UPDATE topics SET status=?,output=?,error=?,finished=datetime('now') WHERE id=? AND status='running'",
                            ("failed" if error else "complete", str(output) if output else None, error, id))

    def retry(self, id):
        with self.db:
            count = self.db.execute("UPDATE topics SET status='pending',error=NULL,started=NULL,finished=NULL WHERE id=? AND status IN ('failed','running')", (id,)).rowcount
            if not count:
                raise ValueError("No failed/running topic with that ID. Stop a running worker before retrying it.")

    def rows(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM topics ORDER BY due,id")]

    def close(self):
        self.db.close()
