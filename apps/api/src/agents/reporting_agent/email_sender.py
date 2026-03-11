"""
邮件推送模块 — 使用 Resend 发送每日推荐邮件。
"""

import logging
from datetime import date

import resend

from src.agents.reporting_agent.email_template import (
    render_recommendation_email,
    render_recommendation_plaintext,
)
from src.core.config import settings

logger = logging.getLogger(__name__)


def _init_resend():
    if settings.RESEND_API_KEY:
        resend.api_key = settings.RESEND_API_KEY


async def send_daily_recommendation_email(
    user_email: str,
    recommendations: list[dict],
    rec_date: date | None = None,
) -> bool:
    """
    发送每日推荐邮件给单个用户。

    recommendations 格式：
    [
        {
            "rank": 1,
            "stock_name": "贵州茅台",
            "stock_code": "600519",
            "final_score": 0.85,
            "reason_short": "量化指标表现突出...",
        },
        ...
    ]
    """
    target_date = rec_date or date.today()

    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured, skipping email to %s", user_email)
        return False

    _init_resend()

    html_content = render_recommendation_email(recommendations, target_date)
    text_content = render_recommendation_plaintext(recommendations, target_date)

    date_str = target_date.strftime("%m月%d日")
    subject = f"今日AI选股推荐 — {date_str}"

    try:
        resend.Emails.send({
            "from": settings.EMAIL_FROM,
            "to": user_email,
            "subject": subject,
            "html": html_content,
            "text": text_content,
        })
        logger.info("Recommendation email sent to %s", user_email)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", user_email)
        return False


async def send_batch_recommendation_emails(
    user_emails: list[str],
    recommendations: list[dict],
    rec_date: date | None = None,
) -> dict:
    """批量发送推荐邮件给多个用户。"""
    sent = 0
    failed = 0
    for email in user_emails:
        ok = await send_daily_recommendation_email(email, recommendations, rec_date)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}
