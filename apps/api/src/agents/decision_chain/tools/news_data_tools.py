from datetime import datetime
from typing import Annotated

import yfinance as yf
from dateutil.relativedelta import relativedelta
from langchain_core.tools import tool


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve news for a specific stock ticker."""
    try:
        stock = yf.Ticker(ticker)
        news = stock.get_news(count=20)
        if not news:
            return f"No news found for {ticker}"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        for article in news:
            data = _extract_article_data(article)
            if data["pub_date"]:
                pub_naive = data["pub_date"].replace(tzinfo=None) if hasattr(data["pub_date"], "replace") else data["pub_date"]
                if not (start_dt <= pub_naive <= end_dt + relativedelta(days=1)):
                    continue
            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"

        if not news_str:
            return f"No news found for {ticker} between {start_date} and {end_date}"
        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """Retrieve global/macro economic news using yfinance Search."""
    search_queries = [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
        "global markets trading",
    ]
    all_news = []
    seen_titles = set()

    try:
        for query in search_queries:
            search = yf.Search(query=query, news_count=limit, enable_fuzzy_query=True)
            if search.news:
                for article in search.news:
                    data = _extract_article_data(article) if "content" in article else None
                    title = data["title"] if data else article.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)
            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = ""
        for article in all_news[:limit]:
            if "content" in article:
                data = _extract_article_data(article)
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")
                summary = ""
            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
    except Exception as e:
        return f"Error fetching global news: {str(e)}"


@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve insider transaction information about a company."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.insider_transactions
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
        csv_string = data.to_csv()
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + csv_string
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def _extract_article_data(article: dict) -> dict:
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return {"title": title, "summary": summary, "publisher": publisher, "link": link, "pub_date": pub_date}
    return {
        "title": article.get("title", "No title"),
        "summary": article.get("summary", ""),
        "publisher": article.get("publisher", "Unknown"),
        "link": article.get("link", ""),
        "pub_date": None,
    }