# Finance Agent API

基于 FastAPI 的后端服务，使用 PostgreSQL 数据库，部署在阿里云轻量服务器上。

## 本地开发

```bash
# 安装依赖
cd apps/api
uv sync

# 配置环境变量（复制模板后填入数据库连接信息）
cp .env.example .env

# 启动开发服务器
pnpm dev
```

## 数据库迁移

修改 `src/models.py` 中的模型后，需要手动生成迁移文件：

```bash
# 生成迁移文件（描述信息用英文）
pnpm --filter api db:revision "add user table"

# 本地执行迁移
pnpm --filter api db:migrate

# 回滚上一次迁移
pnpm --filter api db:rollback
```

迁移文件位于 `alembic/versions/` 目录，**必须提交到 Git**。CI/CD 部署时会自动执行未应用的迁移。

## 部署架构

```
客户端 --HTTPS:443--> Caddy（自动 SSL）--127.0.0.1:8000--> Uvicorn（FastAPI）--localhost:5432--> PostgreSQL
```

- **服务器**：阿里云轻量（2G/2vCPU），Alibaba Cloud Linux 3
- **反向代理**：Caddy（自动管理 Let's Encrypt HTTPS 证书）
- **进程管理**：Systemd
- **域名**：finance.chato-ai.net
- **部署方式**：GitHub Actions push 到 main 自动部署

## 首次部署（仅一次）

### 1. 初始化服务器

SSH 登录服务器，以 root 执行：

```bash
sudo bash /opt/finance-agent/apps/api/deploy/setup.sh
```

脚本会自动完成：创建 deploy 用户、安装 uv/Caddy、配置 Systemd 服务、启动应用。

### 2. 配置数据库密码

```bash
vim /opt/finance-agent/apps/api/.env.prod
```

### 3. 生成 CI/CD 部署密钥

```bash
sudo -u deploy ssh-keygen -t ed25519 -C "github-actions-deploy" -f /home/deploy/.ssh/id_deploy -N ""
sudo -u deploy bash -c 'cat /home/deploy/.ssh/id_deploy.pub >> /home/deploy/.ssh/authorized_keys'
cat /home/deploy/.ssh/id_deploy  # 复制私钥内容
```

### 4. 配置 GitHub Secrets

在仓库 Settings > Secrets and variables > Actions 中添加：

| Secret 名称 | 值 |
|---|---|
| `SERVER_HOST` | 服务器 IP |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | 上一步生成的私钥完整内容 |

### 5. 确保域名和端口

- 域名 `finance.chato-ai.net` 已 DNS 解析到服务器 IP
- 阿里云安全组放行 **80** 和 **443** 端口（Caddy 自动 HTTPS 需要）

## CI/CD 自动部署

push 到 `main` 分支且 `apps/api/` 下有文件变更时，GitHub Actions 自动执行：

1. SSH 连接服务器
2. `git pull origin main`
3. `uv sync`（安装/更新依赖）
4. `alembic upgrade head`（执行数据库迁移）
5. `systemctl restart finance-agent-api`
6. 健康检查 `/health`

## 服务器运维

```bash
# 查看服务状态
systemctl status finance-agent-api

# 查看实时日志
journalctl -u finance-agent-api -f

# 手动重启
sudo systemctl restart finance-agent-api

# 查看 Caddy 状态
systemctl status caddy
```

## 环境配置

| 环境 | 配置文件 | 启动方式 | 数据库连接 |
|---|---|---|---|
| dev（本地开发） | `.env` | 默认 | 远程 IP |
| prod（服务器） | `.env.prod` | `ENV=prod` | localhost |
