from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import find_excel_file, import_questions_from_excel  # noqa: E402


if __name__ == "__main__":
    excel_path = find_excel_file()
    count = import_questions_from_excel(excel_path)
    print(f"已从 {excel_path.name} 导入 {count} 道题。")
