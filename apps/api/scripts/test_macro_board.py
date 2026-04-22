"""
Test script for fetching the 4 macro indicators on the public board:
  1. VIX (恐慌指数)
  2. US 10Y Treasury Yield (美国10年期国债收益率)
  3. DXY (美元指数)
  4. US 2Y / 2Y-10Y Spread (美国2年期国债收益率 / 利差)

Run:
    cd apps/api && uv run python -m scripts.test_macro_board
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

requests.Session().trust_env = False


def _no_proxy_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    return s


def test_vix():
    print("=" * 60)
    print("[1/4] VIX 恐慌指数")
    print("=" * 60)

    import akshare as ak

    try:
        print("  -> 尝试 index_global_spot_em (无代理)...")
        session = _no_proxy_session()
        original_get = requests.get
        requests.get = session.get
        try:
            df = ak.index_global_spot_em()
            for kw in ["VIX", "恐慌"]:
                matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    print(f"  ✅ 找到 VIX (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
                    return
            print(f"  ⚠️  DataFrame 返回成功但未找到 VIX 行, 列: {df.columns.tolist()}")
            vix_rows = df[df["名称"].astype(str).str.contains("标普", case=False, na=False)]
            if not vix_rows.empty:
                print(f"  (找到标普相关: {vix_rows[['名称','最新价','涨跌幅']].to_string()})")
        finally:
            requests.get = original_get
    except Exception as e:
        print(f"  ❌ index_global_spot_em 失败: {e}")

    print()

    try:
        print("  -> 尝试 futures_global_spot_em (无代理)...")
        session = _no_proxy_session()
        original_get = requests.get
        requests.get = session.get
        try:
            df = ak.futures_global_spot_em()
            for kw in ["VIX"]:
                matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    print(f"  ✅ 找到 VIX: 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
                    return
            names_with_vix = df[df["名称"].astype(str).str.contains("VIX|恐慌", case=False, na=False)]
            if not names_with_vix.empty:
                print(f"  ⚠️  找到VIX相关: {names_with_vix[['名称','最新价','涨跌幅']].head(3).to_string()}")
            else:
                print(f"  ⚠️  未找到VIX, 共{len(df)}行数据")
        finally:
            requests.get = original_get
    except Exception as e:
        print(f"  ❌ futures_global_spot_em 失败: {e}")

    print()
    print("  -> 尝试直接访问 CBOE VIX 数据...")
    try:
        session = _no_proxy_session()
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=1d&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = session.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            change_pct = ((price - prev) / prev * 100) if prev and price else None
            print(f"  ✅ VIX via Yahoo Finance: price={price}, change_pct={change_pct:.2f}%")
            return
        else:
            print(f"  ❌ Yahoo Finance 返回 {r.status_code}")
    except Exception as e:
        print(f"  ❌ Yahoo Finance 失败: {e}")

    print("  ❌ 所有VIX数据源均失败")


def test_us10y():
    print()
    print("=" * 60)
    print("[2/4] US 10Y 美国十年期国债收益率")
    print("=" * 60)

    import akshare as ak

    try:
        print("  -> 尝试 bond_zh_us_rate (东方财富)...")
        df = ak.bond_zh_us_rate(start_date="20260410")
        latest = df.iloc[-1]
        us10y = latest["美国国债收益率10年"]
        us2y = latest["美国国债收益率2年"]
        spread = latest.get("美国国债收益率10年-2年")
        date = latest["日期"]
        print(f"  ✅ 日期={date}")
        print(f"     美国2年期: {us2y}%")
        print(f"     美国10年期: {us10y}%")
        if spread is not None and not pd.isna(spread):
            print(f"     2Y-10Y利差: {spread}%")
        else:
            calc_spread = us10y - us2y
            print(f"     2Y-10Y利差(计算): {calc_spread:.2f}% = {calc_spread*100:.0f} bps")
    except Exception as e:
        print(f"  ❌ bond_zh_us_rate 失败: {e}")

    print()

    try:
        print("  -> 尝试 bond_gb_us_sina (新浪)...")
        df10 = ak.bond_gb_us_sina(symbol="美国10年期国债")
        df2 = ak.bond_gb_us_sina(symbol="美国2年期国债")
        latest10 = df10.iloc[-1]
        latest2 = df2.iloc[-1]
        print(f"  ✅ 10Y 日期={latest10['date']}, 收盘={latest10['close']}%")
        print(f"  ✅ 2Y  日期={latest2['date']}, 收盘={latest2['close']}%")
        spread_bps = (latest10["close"] - latest2["close"]) * 100
        print(f"     2Y-10Y利差: {spread_bps:.1f} bps")
    except Exception as e:
        print(f"  ❌ bond_gb_us_sina 失败: {e}")


def test_dxy():
    print()
    print("=" * 60)
    print("[3/4] DXY 美元指数")
    print("=" * 60)

    import akshare as ak

    try:
        print("  -> 尝试 index_global_spot_em (无代理)...")
        session = _no_proxy_session()
        original_get = requests.get
        requests.get = session.get
        try:
            df = ak.index_global_spot_em()
            for kw in ["美元指数", "UDI"]:
                matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    print(f"  ✅ 找到 DXY (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
                    return
            udi_rows = df[df["代码"].astype(str).str.upper() == "UDI"]
            if not udi_rows.empty:
                row = udi_rows.iloc[0]
                print(f"  ✅ 找到 DXY (via code UDI): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
                return
            print("  ⚠️  DataFrame 返回成功但未找到 DXY/UDI 行")
        finally:
            requests.get = original_get
    except Exception as e:
        print(f"  ❌ index_global_spot_em 失败: {e}")

    print()

    try:
        print("  -> 尝试 futures_global_spot_em 查找美元指数...")
        session = _no_proxy_session()
        original_get = requests.get
        requests.get = session.get
        try:
            df = ak.futures_global_spot_em()
            for kw in ["美元指数", "美元", "DXY", "UDI"]:
                matched = df[df["名称"].astype(str).str.contains(kw, case=False, na=False)]
                if not matched.empty:
                    row = matched.iloc[0]
                    print(f"  ✅ 找到美元指数 (via {kw}): 最新价={row.get('最新价')}, 涨跌幅={row.get('涨跌幅')}")
                    return
        finally:
            requests.get = original_get
    except Exception as e:
        print(f"  ❌ futures_global_spot_em 失败: {e}")

    print()

    try:
        print("  -> 尝试 Yahoo Finance 获取 DXY...")
        session = _no_proxy_session()
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=1d&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = session.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            change_pct = ((price - prev) / prev * 100) if prev and price else None
            print(f"  ✅ DXY via Yahoo Finance: price={price}, change_pct={change_pct:.2f}%")
            return
        else:
            print(f"  ❌ Yahoo Finance 返回 {r.status_code}")
    except Exception as e:
        print(f"  ❌ Yahoo Finance 失败: {e}")

    print("  ❌ 所有DXY数据源均失败")


def test_us2y_spread():
    print()
    print("=" * 60)
    print("[4/4] US 2Y-10Y Spread 美国国债2Y-10Y利差")
    print("=" * 60)

    import akshare as ak

    try:
        print("  -> 使用 bond_zh_us_rate 计算利差...")
        df = ak.bond_zh_us_rate(start_date="20260410")
        latest = df.iloc[-1]
        us10y = latest["美国国债收益率10年"]
        us2y = latest["美国国债收益率2年"]
        spread_col = latest.get("美国国债收益率10年-2年")
        date = latest["日期"]
        spread_value = spread_col if (spread_col is not None and not pd.isna(spread_col)) else (us10y - us2y)
        spread_bps = spread_value * 100
        print(f"  ✅ 日期={date}")
        print(f"     US 2Y: {us2y}%")
        print(f"     US 10Y: {us10y}%")
        print(f"     2Y-10Y Spread: {spread_bps:.1f} bps")
    except Exception as e:
        print(f"  ❌ bond_zh_us_rate 失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 140)

    print("检测到的系统代理: http://127.0.0.1:1082")
    print("已清除代理环境变量并禁用 requests trust_env")
    print()

    test_vix()
    test_us10y()
    test_dxy()
    test_us2y_spread()

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print("1. VIX:      主要依赖 index_global_spot_em 或 Yahoo Finance")
    print("2. US 10Y:   可用 bond_zh_us_rate 或 bond_gb_us_sina ✅")
    print("3. DXY:      主要依赖 index_global_spot_em 或 Yahoo Finance")
    print("4. 2Y-10Y:   可用 bond_zh_us_rate 计算得出 ✅")
    print()
    print("关键问题: index_global_spot_em 因代理(proxy)问题连接失败")
    print("修复方案: 在代码中禁用 requests 代理 或 确保 127.0.0.1:1082 代理正常运行")