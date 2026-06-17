from __future__ import annotations

from io import BytesIO
from math import ceil
import os

import pandas as pd
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for

from db import (
    DB_PATH,
    connect,
    fetch_assignment,
    find_excel_file,
    get_assignment_progress,
    get_overall_progress,
    import_questions_from_excel,
    import_questions_from_upload,
    init_assignments,
    init_db,
    now_text,
    status_to_label,
)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "local-review-tool")

VALID_STATUSES = {"pending", "keep", "delete"}
REVIEW_ACTIONS = {"keep", "delete"}
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100


def parse_int(value: str | None, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        number = int(value or default)
    except (TypeError, ValueError):
        number = default
    number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


@app.route("/")
def index():
    return redirect(url_for("admin"))


@app.route("/admin")
def admin():
    excel_file = None
    excel_error = None
    try:
        excel_file = find_excel_file().name
    except FileNotFoundError as exc:
        excel_error = str(exc)

    db_exists = DB_PATH.exists()
    overall = get_overall_progress() if db_exists else {
        "total": 0,
        "pending": 0,
        "keep": 0,
        "delete": 0,
    }
    assignments = get_assignment_progress() if db_exists else []
    return render_template(
        "admin.html",
        db_path=DB_PATH.name,
        db_exists=db_exists,
        excel_file=excel_file,
        excel_error=excel_error,
        overall=overall,
        assignments=assignments,
    )


@app.post("/admin/init-db")
def admin_init_db():
    init_db()
    flash("数据库初始化完成。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/import")
def admin_import():
    try:
        count = import_questions_from_excel()
    except Exception as exc:
        flash(f"导入失败：{exc}", "error")
    else:
        flash(f"导入完成，共 {count} 道题。重新导入会重置全部筛选状态。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/upload-import")
def admin_upload_import():
    upload = request.files.get("excel_file")
    if upload is None or not upload.filename:
        flash("请先选择 Excel 文件。", "error")
        return redirect(url_for("admin"))
    if not upload.filename.lower().endswith((".xlsx", ".xls")):
        flash("只支持上传 .xlsx 或 .xls 文件。", "error")
        return redirect(url_for("admin"))

    try:
        count = import_questions_from_upload(upload)
    except Exception as exc:
        flash(f"上传导入失败：{exc}", "error")
    else:
        flash(f"上传导入完成，共 {count} 道题。重新导入会重置全部筛选状态。", "success")
    return redirect(url_for("admin"))


@app.post("/admin/init-assignments")
def admin_init_assignments():
    count = init_assignments()
    flash(f"分配初始化完成，共 {count} 个筛选人。", "success")
    return redirect(url_for("admin"))


@app.route("/review")
def review():
    reviewer_id = request.args.get("reviewer_id", "").strip()
    return render_template("review.html", reviewer_id=reviewer_id)


@app.get("/api/questions")
def api_questions():
    reviewer_id = request.args.get("reviewer_id", "").strip()
    status = request.args.get("status", "all").strip()
    page = parse_int(request.args.get("page"), 1, 1)
    page_size = parse_int(request.args.get("page_size"), PAGE_SIZE_DEFAULT, 1, PAGE_SIZE_MAX)

    if not reviewer_id:
        return jsonify({"error": "缺少 reviewer_id"}), 400
    if status != "all" and status not in VALID_STATUSES:
        return jsonify({"error": "筛选状态无效"}), 400

    with connect() as conn:
        assignment = fetch_assignment(conn, reviewer_id)
        if assignment is None:
            return jsonify({"error": "未找到该筛选人的分配区间"}), 404

        filters = [
            "question_id BETWEEN ? AND ?",
        ]
        params: list[object] = [
            assignment["start_question_id"],
            assignment["end_question_id"],
        ]
        if status != "all":
            filters.append("review_status = ?")
            params.append(status)

        where_clause = " AND ".join(filters)
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM questions WHERE {where_clause}",
            params,
        ).fetchone()["count"]
        page_count = max(1, ceil(total / page_size)) if total else 1
        page = min(page, page_count)
        offset = (page - 1) * page_size

        rows = conn.execute(
            f"""
            SELECT question_id, subject_code, subject_name, question_type,
                   content, review_status, reviewer_id, reviewed_at
            FROM questions
            WHERE {where_clause}
            ORDER BY question_id
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    questions = [
        {
            "question_id": row["question_id"],
            "subject_code": row["subject_code"],
            "subject_name": row["subject_name"],
            "question_type": row["question_type"],
            "content": row["content"],
            "review_status": row["review_status"],
            "review_status_label": status_to_label(row["review_status"]),
            "reviewer_id": row["reviewer_id"],
            "reviewed_at": row["reviewed_at"],
        }
        for row in rows
    ]
    return jsonify(
        {
            "questions": questions,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "page_count": page_count,
            },
            "assignment": {
                "reviewer_id": assignment["reviewer_id"],
                "start_question_id": assignment["start_question_id"],
                "end_question_id": assignment["end_question_id"],
            },
        }
    )


@app.post("/api/review")
def api_review():
    data = request.get_json(silent=True) or {}
    reviewer_id = str(data.get("reviewer_id", "")).strip()
    action = str(data.get("action", "")).strip()
    try:
        question_id = int(data.get("question_id"))
    except (TypeError, ValueError):
        question_id = 0

    if not reviewer_id:
        return jsonify({"error": "缺少 reviewer_id"}), 400
    if action not in REVIEW_ACTIONS:
        return jsonify({"error": "操作无效"}), 400
    if question_id <= 0:
        return jsonify({"error": "题目序号无效"}), 400

    reviewed_at = now_text()
    with connect() as conn:
        assignment = fetch_assignment(conn, reviewer_id)
        if assignment is None:
            return jsonify({"error": "未找到该筛选人的分配区间"}), 404
        if not assignment["start_question_id"] <= question_id <= assignment["end_question_id"]:
            return jsonify({"error": "不能操作不属于自己区间的题目"}), 403

        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE questions
            SET review_status = ?, reviewer_id = ?, reviewed_at = ?
            WHERE question_id = ?
              AND question_id BETWEEN ? AND ?
            """,
            (
                action,
                reviewer_id,
                reviewed_at,
                question_id,
                assignment["start_question_id"],
                assignment["end_question_id"],
            ),
        )
        conn.commit()

        if cursor.rowcount != 1:
            return jsonify({"error": "题目不存在或不属于当前筛选人"}), 404

    return jsonify(
        {
            "ok": True,
            "question_id": question_id,
            "review_status": action,
            "review_status_label": status_to_label(action),
            "reviewer_id": reviewer_id,
            "reviewed_at": reviewed_at,
        }
    )


@app.get("/api/progress")
def api_progress():
    reviewer_id = request.args.get("reviewer_id", "").strip()
    overall = get_overall_progress()
    result: dict[str, object] = {"overall": overall}

    if reviewer_id:
        with connect() as conn:
            assignment = fetch_assignment(conn, reviewer_id)
            if assignment is None:
                return jsonify({"error": "未找到该筛选人的分配区间"}), 404
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN review_status <> 'pending' THEN 1 ELSE 0 END) AS reviewed,
                    SUM(CASE WHEN review_status = 'keep' THEN 1 ELSE 0 END) AS keep_count,
                    SUM(CASE WHEN review_status = 'delete' THEN 1 ELSE 0 END) AS delete_count
                FROM questions
                WHERE question_id BETWEEN ? AND ?
                """,
                (assignment["start_question_id"], assignment["end_question_id"]),
            ).fetchone()
            result["reviewer"] = {
                "reviewer_id": reviewer_id,
                "start_question_id": assignment["start_question_id"],
                "end_question_id": assignment["end_question_id"],
                "total": int(row["total"] or 0),
                "reviewed": int(row["reviewed"] or 0),
                "keep": int(row["keep_count"] or 0),
                "delete": int(row["delete_count"] or 0),
            }

    return jsonify(result)


@app.get("/export")
def export():
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT question_id, subject_code, subject_name, question_type,
                   content, review_status, reviewer_id, reviewed_at
            FROM questions
            ORDER BY question_id
            """
        ).fetchall()

    data = [
        {
            "题目序号": row["question_id"],
            "考试科目代码": row["subject_code"],
            "考试科目名称": row["subject_name"],
            "试题类型": row["question_type"],
            "试题内容": row["content"],
            "筛选状态": status_to_label(row["review_status"]),
            "筛选人": row["reviewer_id"] or "",
            "筛选时间": row["reviewed_at"] or "",
        }
        for row in rows
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(data).to_excel(writer, index=False, sheet_name="筛选结果")
        worksheet = writer.sheets["筛选结果"]
        worksheet.freeze_panes = "A2"
        for column in worksheet.columns:
            header = str(column[0].value or "")
            width = min(max(len(header) + 4, 12), 50)
            worksheet.column_dimensions[column[0].column_letter].width = width
        worksheet.column_dimensions["E"].width = 80
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="reviewed_tiku.xlsx",
    )


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
