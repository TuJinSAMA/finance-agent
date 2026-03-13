"""
手动触发定时任务（跳过交易日检查）。

用法：
    # 运行单个任务
    cd apps/api && uv run python -m scripts.trigger_job daily_quotes
    cd apps/api && uv run python -m scripts.trigger_job daily_screening

    # 按依赖顺序运行全天流水线
    cd apps/api && uv run python -m scripts.trigger_job all

    # 从某一步开始（跳过之前的步骤）
    cd apps/api && uv run python -m scripts.trigger_job all --from morning_event_scan

    # 只运行下午盘后任务
    cd apps/api && uv run python -m scripts.trigger_job all --from daily_quotes --to technical_indicators

全天流水线执行顺序（按数据依赖）：
    1. daily_quotes           — 拉取当日收盘行情
    2. daily_screening        — 量化筛选 → 关注池 Top 50
    3. technical_indicators   — 计算技术指标
    4. morning_event_scan     — 新闻扫描 + LLM 催化剂分析
    5. daily_recommendation   — 综合评分 → 推荐理由 → 用户分发
    6. rec_performance_tracking — 更新历史推荐 T+1/T+5 收益
"""

import argparse
import asyncio
import logging
import sys
import time

from src.core.job_logger import JobLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trigger_job")

PIPELINE_ORDER = [
    "daily_quotes",
    "daily_screening",
    "technical_indicators",
    "morning_event_scan",
    "daily_recommendation",
    "rec_performance_tracking",
]

JOB_DESCRIPTIONS = {
    "daily_quotes": "拉取当日全市场收盘行情",
    "technical_indicators": "计算全市场技术指标",
    "weekly_sync": "同步股票列表 + 行业 + 上市日期 + 基本面",
    "daily_screening": "量化筛选（硬性过滤 + 多因子打分 → 关注池 Top 50）",
    "morning_event_scan": "新闻扫描 + LLM 催化剂分析 + 持仓异动检测",
    "daily_recommendation": "综合评分 → LLM 推荐理由 → 用户分发 → 邮件推送",
    "rec_performance_tracking": "更新历史推荐 T+1/T+5 收益",
}

# trigger_job.py 中使用的 job_name 到 JobLogger job_id 的映射
# weekly_sync 的 job_id 在 jobs.py 里是 weekly_stock_sync
_JOB_LOG_IDS = {
    "weekly_sync": "weekly_stock_sync",
}

ALL_JOBS = list(JOB_DESCRIPTIONS.keys())


async def run_single_job(job_name: str) -> bool:
    """运行单个 job，返回是否成功。"""
    t0 = time.time()
    job_id = _JOB_LOG_IDS.get(job_name, job_name)
    job_desc = JOB_DESCRIPTIONS.get(job_name, job_name)
    log_id = JobLogger.start(job_id, job_desc)
    try:
        if job_name == "daily_quotes":
            from src.agents.data_agent.jobs import _daily_quotes_async
            await _daily_quotes_async(log_id)

        elif job_name == "technical_indicators":
            from src.agents.data_agent.jobs import _technical_indicators_async
            await _technical_indicators_async(log_id)

        elif job_name == "weekly_sync":
            from src.agents.data_agent.jobs import _weekly_sync_async
            await _weekly_sync_async(log_id)

        elif job_name == "daily_screening":
            from src.agents.orchestrator.jobs import _daily_screening_async
            await _daily_screening_async(log_id)

        elif job_name == "morning_event_scan":
            from src.agents.event_agent.jobs import _morning_event_scan_async
            await _morning_event_scan_async(log_id)

        elif job_name == "daily_recommendation":
            from src.agents.orchestrator.jobs import _daily_recommendation_async
            await _daily_recommendation_async(log_id)

        elif job_name == "rec_performance_tracking":
            from src.agents.orchestrator.jobs import _rec_performance_async
            await _rec_performance_async(log_id)

        else:
            logger.error("Unknown job: %s", job_name)
            JobLogger.fail(log_id, f"Unknown job: {job_name}")
            return False

        elapsed = time.time() - t0
        logger.info("Job '%s' completed in %.1f seconds", job_name, elapsed)
        return True

    except Exception:
        elapsed = time.time() - t0
        logger.exception("Job '%s' FAILED after %.1f seconds", job_name, elapsed)
        return False


async def run_pipeline(from_step: str | None, to_step: str | None):
    """按依赖顺序运行全天流水线。"""
    steps = PIPELINE_ORDER[:]

    if from_step:
        try:
            start_idx = steps.index(from_step)
            steps = steps[start_idx:]
        except ValueError:
            logger.error("Unknown step: %s", from_step)
            return

    if to_step:
        try:
            end_idx = steps.index(to_step)
            steps = steps[: end_idx + 1]
        except ValueError:
            logger.error("Unknown step: %s", to_step)
            return

    total = len(steps)
    logger.info("=" * 60)
    logger.info("Daily Pipeline — %d steps to run", total)
    for i, step in enumerate(steps, 1):
        logger.info("  [%d/%d] %s — %s", i, total, step, JOB_DESCRIPTIONS[step])
    logger.info("=" * 60)

    t_total = time.time()
    results: list[tuple[str, bool, float]] = []

    for i, step in enumerate(steps, 1):
        logger.info("")
        logger.info("━" * 60)
        logger.info("Step %d/%d: %s", i, total, step)
        logger.info("Description: %s", JOB_DESCRIPTIONS[step])
        logger.info("━" * 60)

        t_step = time.time()
        ok = await run_single_job(step)
        elapsed = time.time() - t_step
        results.append((step, ok, elapsed))

        if not ok:
            logger.error("")
            logger.error("Pipeline STOPPED at step '%s'. Fix the issue and resume with:", step)
            logger.error("  uv run python -m scripts.trigger_job all --from %s", step)
            break

    total_elapsed = time.time() - t_total

    logger.info("")
    logger.info("=" * 60)
    logger.info("Pipeline Summary")
    logger.info("=" * 60)
    for step, ok, elapsed in results:
        status = "OK" if ok else "FAILED"
        logger.info("  [%s] %-30s  %.1fs", status, step, elapsed)
    logger.info("-" * 60)
    logger.info("Total time: %.1f seconds (%.1f minutes)", total_elapsed, total_elapsed / 60)

    failed = [r for r in results if not r[1]]
    if failed:
        logger.error("%d step(s) failed!", len(failed))
        sys.exit(1)
    else:
        logger.info("All %d steps completed successfully!", len(results))


def main():
    parser = argparse.ArgumentParser(
        description="手动触发定时任务（跳过交易日检查）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="可用任务:\n" + "\n".join(
            f"  {k:30s} {v}" for k, v in JOB_DESCRIPTIONS.items()
        ),
    )
    parser.add_argument(
        "job",
        choices=ALL_JOBS + ["all"],
        help="要触发的任务名称，或 'all' 运行全天流水线",
    )
    parser.add_argument(
        "--from",
        dest="from_step",
        choices=PIPELINE_ORDER,
        default=None,
        help="(仅 all 模式) 从指定步骤开始",
    )
    parser.add_argument(
        "--to",
        dest="to_step",
        choices=PIPELINE_ORDER,
        default=None,
        help="(仅 all 模式) 执行到指定步骤为止",
    )
    args = parser.parse_args()

    try:
        if args.job == "all":
            logger.info("Running full daily pipeline...")
            asyncio.run(run_pipeline(args.from_step, args.to_step))
        else:
            desc = JOB_DESCRIPTIONS.get(args.job, "")
            logger.info("Manually triggering: %s (%s)", args.job, desc)
            asyncio.run(run_single_job(args.job))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
