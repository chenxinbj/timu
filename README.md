# 本地题库协作筛选工具

这是一个本地可运行的 Flask Web 工具，用于从 Excel 题库导入题目，分配给 10 个筛选人协作筛选，并导出带筛选结果的 Excel。

## 项目结构

```text
.
├── app.py
├── db.py
├── requirements.txt
├── README.md
├── DEPLOY.md
├── Dockerfile
├── render.yaml
├── deploy
│   ├── nginx.conf
│   └── timu-review.service
├── scripts
│   ├── init_db.py
│   ├── import_excel.py
│   └── init_assignments.py
├── static
│   ├── review.js
│   └── style.css
├── templates
│   ├── admin.html
│   └── review.html
└── timu.xlsx
```

## 安装依赖

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 初始化数据

项目会优先读取 `tiku.xlsx`，如果不存在，则读取当前目录已有的 `timu.xlsx`。

```bash
python scripts/init_db.py
python scripts/import_excel.py
python scripts/init_assignments.py
```

初始化后会生成 `review.db`。重新导入题库会清空旧题目和旧筛选结果，并按 Excel 原始顺序重新生成 `question_id`。

在线部署时也可以在管理页使用“上传 Excel 并导入”，这样不需要把题库文件上传到 GitHub。

## 启动 Web 服务

```bash
python app.py
```

默认地址：

- 管理页：<http://127.0.0.1:5000/admin>
- 筛选页：<http://127.0.0.1:5000/review?reviewer_id=reviewer_1>

如果设置了 `ADMIN_PASSWORD`，访问 `/admin` 和 `/export` 时需要先登录管理员账号。

10 个筛选人的入口分别为：

```text
/review?reviewer_id=reviewer_1
/review?reviewer_id=reviewer_2
...
/review?reviewer_id=reviewer_10
```

## 管理功能

管理页支持：

- 初始化数据库
- 从 Excel 导入题库
- 初始化 10 个筛选人的题目分配
- 查看整体进度与各筛选人进度
- 导出筛选结果

服务器部署时请设置：

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD=强密码
SECRET_KEY=随机长字符串
REVIEW_DB_PATH=/data/timu/review.db
ENABLE_SETUP_ACTIONS=0
```

导出接口：

```text
/export
```

导出文件名为 `reviewed_tiku.xlsx`，字段包括题目序号、科目代码、科目名称、试题类型、题干、筛选状态、筛选人、筛选时间。

## 筛选规则

- 每道题只能选择“保留”或“删除”。
- 题干内容只读，不提供修改入口。
- 每页默认显示 50 道题。
- 支持按“全部 / 未处理 / 已保留 / 已删除”筛选。
- 点击按钮后立即保存到 SQLite。
- 服务端会校验筛选人分配区间，不能操作别人负责的题目。

默认分配：

```text
reviewer_1: 1-4000
reviewer_2: 4001-8000
reviewer_3: 8001-12000
...
reviewer_10: 36001-40000
```

## 测试方式

1. 初始化数据库：

   ```bash
   python scripts/init_db.py
   ```

2. 导入题库：

   ```bash
   python scripts/import_excel.py
   ```

   当前 `timu.xlsx` 应导入 38772 道题。

3. 初始化分配：

   ```bash
   python scripts/init_assignments.py
   ```

4. 启动服务并打开筛选页：

   ```bash
   python app.py
   ```

   访问 <http://127.0.0.1:5000/review?reviewer_id=reviewer_1>，检查分页、筛选、进度和按钮保存。

5. 越权接口测试：

   ```bash
   curl -X POST http://127.0.0.1:5000/api/review \
     -H 'Content-Type: application/json' \
     -d '{"reviewer_id":"reviewer_1","question_id":4001,"action":"keep"}'
   ```

   应返回 403。

6. 导出测试：

访问 <http://127.0.0.1:5000/export>，确认下载 `reviewed_tiku.xlsx`。

## 发布到 GitHub

建议只把代码发布到 GitHub，不要上传题库和数据库文件。`.gitignore` 已默认忽略：

- `review.db`
- `tiku.xlsx`
- `timu.xlsx`
- `*.xlsx`
- `.venv/`

首次发布示例：

```bash
git init
git add .
git commit -m "Initial question review tool"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

如果使用 GitHub CLI：

```bash
gh auth login
gh repo create 你的仓库名 --public --source=. --remote=origin --push
```

## 部署到 Render

GitHub Pages 只能托管静态网页，不能运行 Flask 和 SQLite。本项目要让别人在线访问，推荐部署到 Render、Railway、Fly.io 或 VPS。

本项目已包含 `Dockerfile` 和 `render.yaml`，可直接使用 Render Blueprint 部署。

Render 部署步骤：

1. 把项目推送到 GitHub。
2. 打开 <https://render.com>，连接 GitHub。
3. 选择 New Blueprint，选择该仓库。
4. Render 会读取 `render.yaml` 并创建 Web Service。
5. 部署完成后，打开 Render 给出的公开网址。
6. 进入 `/admin`：
   - 点击“初始化数据库”
   - 上传 Excel 并导入
   - 点击“初始化 10 人分配”
7. 把筛选链接发给对应人员，例如：

```text
https://你的服务地址/review?reviewer_id=reviewer_1
https://你的服务地址/review?reviewer_id=reviewer_2
```

`render.yaml` 已配置 SQLite 数据库路径为 `/var/data/review.db`，并挂载 1GB 持久化磁盘。不要把数据库放在普通容器目录，否则服务重启后数据可能丢失。

## 生产环境注意事项

- 服务器部署请优先阅读 [DEPLOY.md](DEPLOY.md)。
- `/admin` 和 `/export` 支持管理员密码保护，公网或内网服务器都应设置 `ADMIN_PASSWORD`。
- 如果题库敏感，不要将 Excel 或导出的结果提交到 GitHub。
- SQLite 适合 10 人以内这种轻量协作筛选；如果未来人数很多或需要复杂权限，建议迁移到 PostgreSQL。
