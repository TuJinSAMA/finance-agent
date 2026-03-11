"""
推荐邮件 HTML 模板。

内联 CSS 以确保邮件客户端兼容性。
"""

from datetime import date


def render_recommendation_email(
    recommendations: list[dict],
    rec_date: date,
) -> str:
    cards_html = ""
    for rec in recommendations:
        stock_name = rec.get("stock_name", "—")
        stock_code = rec.get("stock_code", "")
        rank = rec.get("rank", "—")
        final_score = rec.get("final_score")
        reason_short = rec.get("reason_short", "")

        score_display = f"{float(final_score) * 100:.0f}" if final_score else "—"

        cards_html += f"""
        <tr>
          <td style="padding: 16px 20px; border-bottom: 1px solid #E8E0D4;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td width="40" style="vertical-align: top;">
                  <div style="width: 36px; height: 36px; border-radius: 8px; background-color: #E8F5E9; color: #3A6B5A; font-weight: bold; font-size: 16px; text-align: center; line-height: 36px;">
                    #{rank}
                  </div>
                </td>
                <td style="padding-left: 12px; vertical-align: top;">
                  <div style="font-size: 15px; font-weight: 600; color: #1C1C1C;">
                    {stock_name}
                    <span style="font-size: 12px; color: #8A7E72; font-weight: normal; margin-left: 6px;">{stock_code}</span>
                  </div>
                  <div style="font-size: 13px; color: #555; margin-top: 6px; line-height: 1.5;">
                    {reason_short}
                  </div>
                </td>
                <td width="60" style="text-align: right; vertical-align: top;">
                  <div style="font-size: 20px; font-weight: 700; color: #3A6B5A;">{score_display}</div>
                  <div style="font-size: 10px; color: #8A7E72;">综合评分</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    date_str = rec_date.strftime("%m月%d日")
    date_full = rec_date.strftime("%Y年%m月%d日")

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AlphaDesk 今日推荐 - {date_str}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FAF7F2; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #FAF7F2;">
    <tr>
      <td align="center" style="padding: 32px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 560px; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background-color: #2C3E2D; padding: 24px 20px; text-align: center;">
              <div style="font-size: 20px; font-weight: 700; color: #FAF7F2; letter-spacing: 1px;">ALPHADESK</div>
              <div style="font-size: 13px; color: #6B8F7B; margin-top: 4px;">AI 智能选股推荐</div>
            </td>
          </tr>

          <!-- Date bar -->
          <tr>
            <td style="padding: 16px 20px; background-color: #FAF7F2; border-bottom: 1px solid #E8E0D4;">
              <div style="font-size: 14px; color: #8A7E72;">
                📅 {date_full} · 今日推荐 {len(recommendations)} 只
              </div>
            </td>
          </tr>

          <!-- Recommendation cards -->
          {cards_html}

          <!-- Footer -->
          <tr>
            <td style="padding: 20px; text-align: center; background-color: #FAF7F2;">
              <div style="font-size: 12px; color: #8A7E72; line-height: 1.6;">
                以上推荐基于量化模型分析，不构成投资建议。<br/>
                投资有风险，入市需谨慎。
              </div>
              <div style="margin-top: 12px;">
                <a href="#" style="display: inline-block; padding: 10px 24px; background-color: #3A6B5A; color: #FFFFFF; text-decoration: none; border-radius: 6px; font-size: 13px; font-weight: 600;">
                  打开 AlphaDesk 查看详情
                </a>
              </div>
              <div style="font-size: 11px; color: #B0A89E; margin-top: 16px;">
                © {rec_date.year} AlphaDesk · Shanghai
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_recommendation_plaintext(
    recommendations: list[dict],
    rec_date: date,
) -> str:
    date_str = rec_date.strftime("%Y年%m月%d日")
    lines = [
        f"AlphaDesk 今日AI选股推荐 — {date_str}",
        f"共 {len(recommendations)} 只推荐",
        "=" * 40,
        "",
    ]
    for rec in recommendations:
        rank = rec.get("rank", "—")
        name = rec.get("stock_name", "—")
        code = rec.get("stock_code", "")
        reason = rec.get("reason_short", "")
        score = rec.get("final_score")
        score_str = f"{float(score) * 100:.0f}" if score else "—"

        lines.append(f"#{rank} {name}（{code}）  综合评分：{score_str}")
        if reason:
            lines.append(f"   {reason}")
        lines.append("")

    lines.extend([
        "-" * 40,
        "以上推荐基于量化模型分析，不构成投资建议。",
        "投资有风险，入市需谨慎。",
        "",
        "© AlphaDesk",
    ])
    return "\n".join(lines)
