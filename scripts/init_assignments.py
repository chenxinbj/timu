from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import init_assignments  # noqa: E402


if __name__ == "__main__":
    count = init_assignments(reviewer_count=10, questions_per_reviewer=4000)
    print(f"筛选人分配初始化完成，共 {count} 人。")
