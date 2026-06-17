from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
from typing import Iterator

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("REVIEW_DB_PATH", BASE_DIR / "review.db"))
EXCEL_CANDIDATES = ("tiku.xlsx", "timu.xlsx")

STATUS_LABELS = {
    "pending": "未处理",
    "keep": "保留",
    "delete": "删除",
}

REQUIRED_COLUMNS = {
    "考试科目代码": "subject_code",
    "考试科目名称": "subject_name",
    "试题类型": "question_type",
    "试题内容": "content",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_excel_file() -> Path:
    for filename in EXCEL_CANDIDATES:
        path = BASE_DIR / filename
        if path.exists():
            return path
    names = "、".join(EXCEL_CANDIDATES)
    raise FileNotFoundError(f"未找到题库文件，请将 {names} 放到项目目录。")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL UNIQUE,
                subject_code TEXT,
                subject_name TEXT,
                question_type TEXT,
                content TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (review_status IN ('pending', 'keep', 'delete')),
                reviewer_id TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reviewer_id TEXT NOT NULL UNIQUE,
                start_question_id INTEGER NOT NULL,
                end_question_id INTEGER NOT NULL,
                CHECK (start_question_id <= end_question_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(review_status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_questions_reviewer ON questions(reviewer_id)"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_assignments_range
            ON review_assignments(start_question_id, end_question_id)
            """
        )
        conn.commit()


def import_questions_from_excel(excel_path: Path | None = None) -> int:
    init_db()
    path = excel_path or find_excel_file()
    df = pd.read_excel(path, dtype=str).fillna("")
    return import_questions_from_dataframe(df)


def import_questions_from_upload(file_storage) -> int:
    init_db()
    df = pd.read_excel(file_storage, dtype=str).fillna("")
    return import_questions_from_dataframe(df)


def import_questions_from_dataframe(df: pd.DataFrame) -> int:
    missing = [name for name in REQUIRED_COLUMNS if name not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少必要字段：{', '.join(missing)}")

    rows = []
    created_at = now_text()
    for index, record in df.iterrows():
        rows.append(
            (
                int(index) + 1,
                str(record["考试科目代码"]).strip(),
                str(record["考试科目名称"]).strip(),
                str(record["试题类型"]).strip(),
                str(record["试题内容"]).strip(),
                "pending",
                created_at,
            )
        )

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM questions")
        conn.executemany(
            """
            INSERT INTO questions (
                question_id, subject_code, subject_name, question_type,
                content, review_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def init_assignments(reviewer_count: int = 10, questions_per_reviewer: int = 4000) -> int:
    init_db()
    rows = []
    for reviewer_number in range(1, reviewer_count + 1):
        start = (reviewer_number - 1) * questions_per_reviewer + 1
        end = reviewer_number * questions_per_reviewer
        rows.append((f"reviewer_{reviewer_number}", start, end))

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM review_assignments")
        conn.executemany(
            """
            INSERT INTO review_assignments (
                reviewer_id, start_question_id, end_question_id
            )
            VALUES (?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def fetch_assignment(conn: sqlite3.Connection, reviewer_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT reviewer_id, start_question_id, end_question_id
        FROM review_assignments
        WHERE reviewer_id = ?
        """,
        (reviewer_id,),
    ).fetchone()


def status_to_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def get_overall_progress() -> dict[str, int]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN review_status = 'keep' THEN 1 ELSE 0 END) AS keep_count,
                SUM(CASE WHEN review_status = 'delete' THEN 1 ELSE 0 END) AS delete_count
            FROM questions
            """
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "pending": int(row["pending"] or 0),
            "keep": int(row["keep_count"] or 0),
            "delete": int(row["delete_count"] or 0),
        }


def get_assignment_progress() -> list[dict[str, int | str]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.reviewer_id,
                a.start_question_id,
                a.end_question_id,
                COUNT(q.id) AS total,
                SUM(CASE WHEN q.review_status <> 'pending' THEN 1 ELSE 0 END) AS reviewed,
                SUM(CASE WHEN q.review_status = 'keep' THEN 1 ELSE 0 END) AS keep_count,
                SUM(CASE WHEN q.review_status = 'delete' THEN 1 ELSE 0 END) AS delete_count
            FROM review_assignments a
            LEFT JOIN questions q
              ON q.question_id BETWEEN a.start_question_id AND a.end_question_id
            GROUP BY a.id
            ORDER BY a.start_question_id
            """
        ).fetchall()
        return [
            {
                "reviewer_id": row["reviewer_id"],
                "start_question_id": row["start_question_id"],
                "end_question_id": row["end_question_id"],
                "total": int(row["total"] or 0),
                "reviewed": int(row["reviewed"] or 0),
                "keep": int(row["keep_count"] or 0),
                "delete": int(row["delete_count"] or 0),
            }
            for row in rows
        ]
