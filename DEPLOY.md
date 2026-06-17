# 服务器部署说明

本文档面向接手部署的技术人员。目标是把题库筛选工具部署到 Linux 服务器，并使用 SQLite 文件保存筛选数据。

## 1. 交付包内容

代码目录应包含：

```text
app.py
db.py
requirements.txt
scripts/
static/
templates/
deploy/
.env.example
```

如果需要带着现有数据上线，还需要单独交付：

```text
review.db
```

题库 Excel 和数据库通常包含业务数据，不建议提交到 GitHub。请通过内网文件、压缩包或服务器安全拷贝方式交付。

## 2. 服务器准备

以下命令以 Ubuntu/Debian 为例：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

建议部署目录：

```text
/opt/timu-review     # 代码
/data/timu           # SQLite 数据库和备份
/etc/timu-review.env # 环境变量
```

创建目录：

```bash
sudo mkdir -p /opt/timu-review /data/timu
sudo chown -R www-data:www-data /opt/timu-review /data/timu
```

## 3. 上传代码和数据库

把代码放到：

```text
/opt/timu-review
```

如果已有本地数据库，请先停止本地 Flask 服务，再复制 `review.db`。服务器上放到：

```text
/data/timu/review.db
```

并设置权限：

```bash
sudo chown www-data:www-data /data/timu/review.db
sudo chmod 660 /data/timu/review.db
```

如果没有现成数据库，可以上线后在 `/admin` 上传 Excel 并导入。

## 4. 安装依赖

```bash
cd /opt/timu-review
sudo -u www-data python3 -m venv .venv
sudo -u www-data .venv/bin/pip install -r requirements.txt
```

## 5. 配置环境变量

复制示例：

```bash
sudo cp /opt/timu-review/.env.example /etc/timu-review.env
```

编辑：

```bash
sudo nano /etc/timu-review.env
```

至少修改：

```text
SECRET_KEY=生成一个随机长字符串
ADMIN_USERNAME=admin
ADMIN_PASSWORD=设置一个强密码
REVIEW_DB_PATH=/data/timu/review.db
FLASK_DEBUG=0
ENABLE_SETUP_ACTIONS=0
```

生成 `SECRET_KEY`：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

保护环境变量文件：

```bash
sudo chown root:www-data /etc/timu-review.env
sudo chmod 640 /etc/timu-review.env
```

## 6. 初始化数据库

如果已经复制了 `review.db`，可跳过本步骤。

如果需要空库：

```bash
cd /opt/timu-review
sudo -u www-data REVIEW_DB_PATH=/data/timu/review.db .venv/bin/python scripts/init_db.py
sudo -u www-data REVIEW_DB_PATH=/data/timu/review.db .venv/bin/python scripts/init_assignments.py
```

也可以启动服务后进入 `/admin`：

1. 初始化数据库
2. 上传 Excel 并导入
3. 初始化 10 人分配

## 7. 配置 systemd

复制服务文件：

```bash
sudo cp /opt/timu-review/deploy/timu-review.service /etc/systemd/system/timu-review.service
sudo systemctl daemon-reload
sudo systemctl enable --now timu-review
```

查看状态：

```bash
sudo systemctl status timu-review
sudo journalctl -u timu-review -f
```

本服务默认监听：

```text
127.0.0.1:8000
```

## 8. 配置 Nginx

复制示例：

```bash
sudo cp /opt/timu-review/deploy/nginx.conf /etc/nginx/sites-available/timu-review
sudo ln -s /etc/nginx/sites-available/timu-review /etc/nginx/sites-enabled/timu-review
```

编辑 `server_name`：

```bash
sudo nano /etc/nginx/sites-available/timu-review
```

检查并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

如果 Excel 文件较大，可以按需调大 `client_max_body_size`。

## 9. 验收地址

管理页：

```text
http://服务器域名/admin
```

筛选页示例：

```text
http://服务器域名/review?reviewer_id=reviewer_1
```

10 个筛选人：

```text
/review?reviewer_id=reviewer_1
/review?reviewer_id=reviewer_2
...
/review?reviewer_id=reviewer_10
```

## 10. 备份和恢复

筛选期间建议每天备份 SQLite：

```bash
sudo systemctl stop timu-review
sudo cp /data/timu/review.db /data/timu/review.db.backup-$(date +%Y%m%d-%H%M%S)
sudo systemctl start timu-review
```

恢复：

```bash
sudo systemctl stop timu-review
sudo cp /data/timu/review.db.backup-YYYYMMDD-HHMMSS /data/timu/review.db
sudo chown www-data:www-data /data/timu/review.db
sudo chmod 660 /data/timu/review.db
sudo systemctl start timu-review
```

## 11. 注意事项

- 公网或内网部署都必须设置 `ADMIN_PASSWORD`。
- `/admin` 和 `/export` 已受管理员登录保护。
- 已导入好题库并上线后，建议设置 `ENABLE_SETUP_ACTIONS=0`，这样管理页会隐藏并禁用初始化数据库、导入题库、上传 Excel、初始化分配等危险操作。
- 筛选链接仍通过 `reviewer_id` 区分人员，请不要把不属于某人的链接发给他人。
- SQLite 适合当前 10 人轻量协作；若未来人数明显增加，建议迁移到 PostgreSQL。
- 不要把 `review.db`、Excel 题库、导出结果提交到公开仓库。
