"""Quick integration test for the decision chain.

Usage:
    cd apps/api && uv run python -m scripts.test_decision_chain AAPL

Requires OPENROUTER_API_KEY in .env
"""
import sys
from src.agents.decision_chain.graph import TradingDecisionChain


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    trade_date = sys.argv[2] if len(sys.argv) > 2 else "2026-01-15"

    print(f"Running decision chain for {ticker} on {trade_date}...")
    chain = TradingDecisionChain()
    final_state, rating = chain.propagate(ticker, trade_date)

    print(f"\n{'='*60}")
    print(f"FINAL RATING: {rating}")
    print(f"{'='*60}")
    print(f"\nMarket Report (first 200 chars): {final_state.get('market_report', '')[:200]}...")
    print(f"Sentiment Report (first 200 chars): {final_state.get('sentiment_report', '')[:200]}...")
    print(f"News Report (first 200 chars): {final_state.get('news_report', '')[:200]}...")
    print(f"Fundamentals Report (first 200 chars): {final_state.get('fundamentals_report', '')[:200]}...")
    print(f"Investment Plan (first 200 chars): {final_state.get('investment_plan', '')[:200]}...")
    print(f"Trader Plan (first 200 chars): {final_state.get('trader_investment_plan', '')[:200]}...")
    print(f"Final Decision (first 300 chars): {final_state.get('final_trade_decision', '')[:300]}...")
    print(f"\nInvestment Debate count: {final_state['investment_debate_state']['count']}")
    print(f"Risk Debate count: {final_state['risk_debate_state']['count']}")


if __name__ == "__main__":
    main()