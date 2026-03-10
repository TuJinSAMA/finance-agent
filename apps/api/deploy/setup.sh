#!/usr/bin/env bash
#
# 首次服务器初始化脚本 — 以 root 身份执行
# 用法: sudo bash setup.sh
#
# 前置条件（需手动完成）:
#   1. 创建 deploy 用户的 SSH 密钥对，公钥添加到 GitHub Deploy Keys
#   2. 配置 deploy 用户的 ~/.ssh/config 指定 GitHub 使用的 IdentityFile
#   3. 将 CI 用的公钥添加到 deploy 用户的 ~/.ssh/authorized_keys
#
set -euo pipefail

REPO_URL="git@github.com:TuJinSAMA/finance-agent.git"
APP_DIR="/opt/finance-agent"
API_DIR="${APP_DIR}/apps/api"
DEPLOY_USER="deploy"

echo "========== 1. 创建 deploy 用户 =========="
if ! id "${DEPLOY_USER}" &>/dev/null; then
    useradd -m -s /bin/bash "${DEPLOY_USER}"
    echo "用户 ${DEPLOY_USER} 已创建"
else
    echo "用户 ${DEPLOY_USER} 已存在，跳过"
fi

echo "========== 2. 配置 sudoers（仅允许管理服务） =========="
cat > /etc/sudoers.d/finance-agent <<'SUDOERS'
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart finance-agent-api
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop finance-agent-api
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl start finance-agent-api
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl status finance-agent-api
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
SUDOERS
chmod 440 /etc/sudoers.d/finance-agent

echo "========== 3. 安装 uv =========="
if ! test -f /usr/local/bin/uv; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    cp /root/.local/bin/uv /usr/local/bin/uv
    cp /root/.local/bin/uvx /usr/local/bin/uvx
    echo "uv 已安装到 /usr/local/bin/"
else
    echo "uv 已存在，跳过"
fi

echo "========== 4. 安装 Caddy =========="
if ! command -v caddy &>/dev/null; then
    dnf install -y 'dnf-command(copr)'
    dnf copr enable -y @caddy/caddy epel-8-x86_64
    dnf install -y caddy
    echo "Caddy 已安装"
else
    echo "Caddy 已存在，跳过"
fi

echo "========== 5. 克隆代码 =========="
if [ ! -d "${APP_DIR}" ]; then
    sudo -u ${DEPLOY_USER} git clone "${REPO_URL}" "${APP_DIR}"
else
    echo "代码目录已存在，跳过克隆"
fi
chown -R ${DEPLOY_USER}:${DEPLOY_USER} "${APP_DIR}"

echo "========== 6. 安装 Python 依赖 =========="
cd "${API_DIR}"
sudo -u ${DEPLOY_USER} /usr/local/bin/uv sync

echo "========== 7. 创建 .env.prod =========="
if [ ! -f "${API_DIR}/.env.prod" ]; then
    cat > "${API_DIR}/.env.prod" <<'ENV'
ENV=prod
DATABASE_URL=postgresql+asyncpg://admin:YOUR_PASSWORD@localhost:5432/finance_agent_db
ENV
    chown ${DEPLOY_USER}:${DEPLOY_USER} "${API_DIR}/.env.prod"
    chmod 600 "${API_DIR}/.env.prod"
    echo "⚠️  请编辑 ${API_DIR}/.env.prod 填入正确的数据库密码"
else
    echo ".env.prod 已存在，跳过"
fi

echo "========== 8. 配置 Systemd 服务 =========="
cp "${API_DIR}/deploy/finance-agent-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable finance-agent-api

echo "========== 9. 配置 Caddy =========="
cp "${API_DIR}/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl enable caddy
systemctl restart caddy

echo "========== 10. 运行数据库迁移并启动服务 =========="
cd "${API_DIR}"
sudo -u ${DEPLOY_USER} ENV=prod /usr/local/bin/uv run alembic upgrade head
systemctl start finance-agent-api

echo ""
echo "=========================================="
echo "  初始化完成！"
echo "=========================================="
echo ""
echo "查看服务状态: systemctl status finance-agent-api"
echo "查看服务日志: journalctl -u finance-agent-api -f"
