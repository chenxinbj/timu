from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DB_PATH, init_db  # noqa: E402


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化完成：{DB_PATH}")
