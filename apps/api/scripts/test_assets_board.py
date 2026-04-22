"""
Test script for fetching asset data on the public board:
  1. S&P 500 (标普500)
  2. NASDAQ (纳斯达克)
  3. Gold (黄金)
  4. WTI Crude Oil (原油)
  5. BTC (比特币) - reference, already working

Only BTC currently has data via akshare crypto_js_spot().
The rest go through index_global_spot_em() which fails for commodities.

Run:
    cd apps/api && uv run python -m scripts.test_assets_board
"""

import os
import traceback

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("all_proxy", None)

import pandas as pd
import requests

s = requests.Session()
s.trust_env = False
s.proxies = {"http": None, "https": None}

_original_get = requests.get
_original_session_get = requests.Session.get


def _install_bypass():
    requests.get = s.get
    requests.Session.get = lambda self, url, **kw: _original_session_get(
        self, url, proxies={"http": None, "https": None}, **kw
    )


_install_bypass()

YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

YAHOO_SYMBOLS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "Gold": "GC=F",
    "WTI": "CL=F",
    "BTC": "BTC-USD",
}


def _yahoo_finance_fetch(name: str, symbol: str) -> dict | None:
    import urllib.parse

    url = f"{YAHOO_BASE}/{urllib.parse.quote(symbol)}"
    params = {"range": "2d", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = s.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"    ❌ Yahoo Finance returned {r.status_code}")
            return None
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            print(f"    ❌ Yahoo Finance: no result")
            return None
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        if price is None:
            print(f"    ❌ Yahoo Finance: no price")
            return None
        change_pct = ((price - prev) / prev * 100) if prev else None
        print(f"    ✅ Yahoo Finance: price={price}, prev={prev}, change_pct={change_pct:.2f}%")
        return {"price": price, "prev": prev, "change_pct": change_pct}
    except Exception as e:
        print(f"    ❌ Yahoo Finance failed: {e}")
        return None


def test_spx():
    print("=" * 60)
    print("[1/5] S&P 500 标普500")
    print("=" * 60)

    name = "S&P 500"
    symbol = "^GSPC"

    # Method 1: akshare index_global_spot_em
    try:
        import akshare as ak

        print("  -> akshare index_global_spot_em...")
        df = ak.index_global_spot_em()
        for kw in ["标普", "S&P", "SPX"]:
            matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
            if not matched.empty:
                row = matched.iloc[0]
                print(
                    f"  ✅ Found (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}"
                )
                break
        else:
            code_matched = df[df["代码"].astype(str).str.upper() == "SPX"]
            if not code_matched.empty:
                row = code_matched.iloc[0]
                print(f"  ✅ Found (via code SPX): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
            else:
                print(f"  ⚠️  DataFrame OK but no S&P 500 row found")
    except Exception as e:
        print(f"  ❌ index_global_spot_em failed: {e}")

    # Method 2: Yahoo Finance
    print("  -> Yahoo Finance...")
    _yahoo_finance_fetch(name, symbol)


def test_nasdaq():
    print()
    print("=" * 60)
    print("[2/5] NASDAQ 纳斯达克")
    print("=" * 60)

    name = "NASDAQ"
    symbol = "^IXIC"

    # Method 1: akshare index_global_spot_em
    try:
        import akshare as ak

        print("  -> akshare index_global_spot_em...")
        df = ak.index_global_spot_em()
        for kw in ["纳斯达克", "NDX"]:
            matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
            if not matched.empty:
                row = matched.iloc[0]
                print(
                    f"  ✅ Found (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}"
                )
                break
        else:
            code_matched = df[df["代码"].astype(str).str.upper() == "NDX"]
            if not code_matched.empty:
                row = code_matched.iloc[0]
                print(f"  ✅ Found (via code NDX): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
            else:
                print(f"  ⚠️  DataFrame OK but no NASDAQ row found")
    except Exception as e:
        print(f"  ❌ index_global_spot_em failed: {e}")

    # Method 2: Yahoo Finance
    print("  -> Yahoo Finance...")
    _yahoo_finance_fetch(name, symbol)


def test_gold():
    print()
    print("=" * 60)
    print("[3/5] Gold 黄金")
    print("=" * 60)

    name = "Gold"
    symbol = "GC=F"

    # Method 1: akshare futures_global_spot_em (commodities are futures, not indices)
    try:
        import akshare as ak

        print("  -> akshare futures_global_spot_em...")
        df = ak.futures_global_spot_em()
        for kw in ["黄金", "Gold", "COMEX黄金", "XAUUSD"]:
            matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
            if not matched.empty:
                row = matched.iloc[0]
                print(
                    f"  ✅ Found (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}"
                )
                break
        else:
            print(f"  ⚠️  futures_global_spot_em OK but no Gold row found")
            gold_rows = df[df["名称"].astype(str).str.contains("金|Gold|XAU", case=False, na=False)]
            if not gold_rows.empty:
                print(f"  (Found gold-related rows: {gold_rows[['名称', '最新价', '涨跌幅']].head(3).to_string()})")
    except Exception as e:
        print(f"  ❌ futures_global_spot_em failed: {e}")

    # Method 2: akshare spot_hist for gold (东方财富)
    try:
        import akshare as ak

        print("  -> akshare spot_hist (黄金9999)...")
        df = ak.spot_hist(symbol="黄金9999")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            print(f"  ✅ spot_hist: date={latest.get('日期')}, close={latest.get('收盘')}")
        else:
            print(f"  ⚠️  spot_hist returned empty")
    except Exception as e:
        print(f"  ❌ spot_hist failed: {e}")

    # Method 3: akshare fx_spot_quote (汇率+贵金属现货)
    try:
        import akshare as ak

        print("  -> akshare fx_spot_quote...")
        df = ak.fx_spot_quote()
        for kw in ["黄金", "Gold", "XAU"]:
            matched = df[df.columns[df.columns.str.contains(kw)]]
            if not matched.empty:
                print(f"  ✅ Found gold data via fx_spot_quote")
                break
    except Exception as e:
        print(f"  ❌ fx_spot_quote failed: {e}")

    # Method 4: Yahoo Finance
    print("  -> Yahoo Finance...")
    _yahoo_finance_fetch(name, symbol)

    # Method 5: akshare gold spot price via 东方财富
    try:
        import akshare as ak

        print("  -> akshare macro_fx_gold (东方财富黄金)...")
        # Try macro China gold price
        df = ak.macro_fx_gold()
        if df is not None and not df.empty:
            print(f"  ✅ macro_fx_gold: columns={df.columns.tolist()}")
            print(f"     Last 3 rows:\n{df.tail(3).to_string()}")
        else:
            print(f"  ⚠️  macro_fx_gold returned empty")
    except Exception as e:
        print(f"  ❌ macro_fx_gold failed: {e}")

    # Method 6: Try akshare forex currencies which may include XAU
    try:
        import akshare as ak

        print("  -> akshare currency_latest (新浪外汇)...")
        df = ak.currency_latest()
        if df is not None and not df.empty:
            gold_rows = df[df["名称"].astype(str).str.contains("黄金|XAU", case=False, na=False)]
            if not gold_rows.empty:
                row = gold_rows.iloc[0]
                print(f"  ✅ Found gold: {row.to_dict()}")
            else:
                print(f"  ⚠️  currency_latest: no gold rows, cols={df.columns.tolist()}")
    except Exception as e:
        print(f"  ❌ currency_latest failed: {e}")


def test_wti():
    print()
    print("=" * 60)
    print("[4/5] WTI Crude Oil 原油")
    print("=" * 60)

    name = "WTI"
    symbol = "CL=F"

    # Method 1: akshare futures_global_spot_em
    try:
        import akshare as ak

        print("  -> akshare futures_global_spot_em...")
        df = ak.futures_global_spot_em()
        for kw in ["原油", "Crude", "WTI", "CL"]:
            matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
            if not matched.empty:
                row = matched.iloc[0]
                print(
                    f"  ✅ Found (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}"
                )
                break
        else:
            print(f"  ⚠️  futures_global_spot_em OK but no WTI/Crude row found")
            oil_rows = df[df["名称"].astype(str).str.contains("油|Oil|WTI|CL", case=False, na=False)]
            if not oil_rows.empty:
                print(f"  (Found oil-related rows: {oil_rows[['名称', '最新价', '涨跌幅']].head(3).to_string()})")
    except Exception as e:
        print(f"  ❌ futures_global_spot_em failed: {e}")

    # Method 2: akshare energy data
    try:
        import akshare as ak

        print("  -> akshare macro_china_oil (中国油价)...")
        df = ak.macro_china_oil()
        if df is not None and not df.empty:
            print(f"  ✅ macro_china_oil: columns={df.columns.tolist()}")
            print(f"     Last 3 rows:\n{df.tail(3).to_string()}")
        else:
            print(f"  ⚠️  macro_china_oil returned empty")
    except Exception as e:
        print(f"  ❌ macro_china_oil failed: {e}")

    # Method 3: Yahoo Finance
    print("  -> Yahoo Finance...")
    _yahoo_finance_fetch(name, symbol)


def test_btc():
    print()
    print("=" * 60)
    print("[5/5] BTC 比特币 (reference - already working)")
    print("=" * 60)

    # Method 1: akshare crypto_js_spot (current working method)
    try:
        import akshare as ak

        print("  -> akshare crypto_js_spot...")
        df = ak.crypto_js_spot()
        if df is not None and not df.empty:
            exact = df[df["交易品种"].astype(str).str.upper() == "BTCUSD"]
            if not exact.empty:
                row = exact.iloc[0]
                print(f"  ✅ Found BTCUSD: 最新报价={row.get('最近报价')}, 涨跌幅={row.get('涨跌幅')}")
            else:
                btc_rows = df[df["交易品种"].astype(str).str.contains("BTC", case=False, na=False)]
                if not btc_rows.empty:
                    row = btc_rows.iloc[0]
                    print(f"  ✅ Found BTC: 最近报价={row.get('最近报价')}, 涨跌幅={row.get('涨跌幅')}")
        else:
            print(f"  ⚠️  crypto_js_spot returned empty")
    except Exception as e:
        print(f"  ❌ crypto_js_spot failed: {e}")

    # Method 2: Yahoo Finance
    print("  -> Yahoo Finance...")
    _yahoo_finance_fetch("BTC", "BTC-USD")


if __name__ == "__main__":
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 140)

    print("Testing free data sources for assets snapshot")
    print("Currently only BTC has reliable data via akshare crypto_js_spot()")
    print()

    test_spx()
    test_nasdaq()
    test_gold()
    test_wti()
    test_btc()

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print("SPX:    index_global_spot_em or Yahoo Finance ^GSPC")
    print("NASDAQ: index_global_spot_em or Yahoo Finance ^IXIC")
    print("GOLD:   futures_global_spot_em or Yahoo Finance GC=F")
    print("WTI:    futures_global_spot_em or Yahoo Finance CL=F")
    print("BTC:    crypto_js_spot ✅ (already working)")
    print()
    print("KEY FINDING: GOLD and WTI are commodities, not global indices.")
    print("They need different akshare functions (e.g. futures_global_spot_em)")
    print("or Yahoo Finance as fallback.")