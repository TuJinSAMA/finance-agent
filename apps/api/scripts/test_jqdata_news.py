"""
测试 JQData 新闻联播文本接口是否可用。

用法：
    cd apps/api && uv run python -m scripts.test_jqdata_news

测试内容：
    1. 登录 JQData（验证账号密码是否正确）
    2. 查询当日或最近一条新闻联播数据（finance.CCTV_NEWS）
    3. 打印结果，确认接口可用性
"""

import asyncio
import logging
import os
import sys
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("test_jqdata_news")


def _load_env() -> tuple[str, str]:
    """从 .env 文件读取 JQDATA_USERNAME / JQDATA_PASSWORD。"""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    username, password = "", ""
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("JQDATA_USERNAME="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("JQDATA_PASSWORD="):
                    password = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    # 环境变量优先级更高
    username = os.getenv("JQDATA_USERNAME", username)
    password = os.getenv("JQDATA_PASSWORD", password)
    return username, password


def test_cctv_news():
    """同步测试主函数（jqdatasdk 是同步库）。"""
    import jqdatasdk as jq
    from jqdatasdk import finance, query

    # ── 1. 登录 ─────────────────────────────────────────────
    username, password = _load_env()
    if not username or not password:
        logger.error(
            "未找到 JQDATA_USERNAME / JQDATA_PASSWORD，"
            "请在 apps/api/.env 中配置或设置环境变量。"
        )
        sys.exit(1)

    logger.info("正在登录 JQData（账号：%s）...", username)
    jq.auth(username, password)
    logger.info("登录成功 ✓")

    # ── 2. 查询剩余流量 ──────────────────────────────────────
    count_info = jq.get_query_count()
    logger.info("当日流量：总 %s 条，剩余 %s 条", count_info.get("total"), count_info.get("spare"))

    # ── 3. 查询最近有数据的一天的新闻联播 ───────────────────────
    # 往前最多找 30 天，找到第一个有数据的交易日
    found_date = None
    df = None
    for days_back in range(0, 30):
        check_date = (date.today() - timedelta(days=days_back)).isoformat()
        logger.info("尝试查询 %s 的新闻联播数据...", check_date)
        try:
            df = finance.run_query(
                query(finance.CCTV_NEWS)
                .filter(finance.CCTV_NEWS.day == check_date)
                .limit(5)
            )
            if df is not None and not df.empty:
                found_date = check_date
                break
        except Exception as e:
            logger.warning("查询 %s 失败：%s", check_date, e)

    if df is None or df.empty:
        logger.warning("最近 30 天内未找到新闻联播数据，接口可能不在权限范围内。")
        sys.exit(0)

    # ── 4. 打印结果 ──────────────────────────────────────────
    logger.info("找到 %s 的新闻联播数据，共 %d 条：", found_date, len(df))
    print("\n" + "=" * 60)
    print(f"日期：{found_date}")
    print("=" * 60)
    for _, row in df.iterrows():
        print(f"\n【标题】{row.get('title', '')}")
        content = str(row.get("content", "") or "")
        preview = content[:200].replace("\n", " ").replace("\r", "")
        if len(content) > 200:
            preview += "..."
        print(f"【正文预览】{preview}")
    print("\n" + "=" * 60)
    logger.info("测试完成 ✓  接口可用，可作为市场情绪参考数据。")


if __name__ == "__main__":
    test_cctv_news()
