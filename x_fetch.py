"""免费 X/Twitter + 新闻搜索 — 基于 WebSearch + DuckDuckGo
不花钱，直接抓取 ETH 相关讨论和新闻
"""
import urllib.request, json, re, ssl
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
PROXY = "http://127.0.0.1:7897"


def _get(url, timeout=15):
    """HTTP GET with proxy fallback"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)

    ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(ph)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except:
        opener2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener2.open(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")


def search_crypto_news(keywords="ETH+crypto+breaking", max_results=8):
    """用 DuckDuckGo 搜加密新闻（免费、无 API key）"""
    results = []
    try:
        # DuckDuckGo HTML search (lite version, no JS)
        url = f"https://lite.duckduckgo.com/lite/?q={keywords}+when:1d"
        html = _get(url, timeout=10)

        # Extract links and titles
        titles = re.findall(r'<a[^>]*class="result-link"[^>]*>(.*?)</a>', html)
        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
        links = re.findall(r'<a[^>]*class="result-link"[^>]*href="([^"]*)"', html)

        for i in range(min(len(titles), max_results)):
            title = re.sub(r'<[^>]+>', '', titles[i]).strip()
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
            link = links[i] if i < len(links) else ""

            # Filter for crypto/ETH relevance
            if any(kw.lower() in (title + snippet).lower() for kw in
                   ["eth", "ethereum", "crypto", "bitcoin", "btc", "blockchain",
                    "以太", "加密", "比特币", "defi", "nft", "sec", "etf"]):
                results.append({
                    "title": title[:120],
                    "snippet": snippet[:200],
                    "link": link,
                    "time": datetime.now(TZ).strftime("%H:%M")
                })
    except Exception as e:
        pass

    return results[:max_results]


def search_x_trending():
    """搜索 X/Twitter 上加密相关趋势（通过搜索引擎间接获取）"""
    results = []
    try:
        # Search for X/Twitter crypto posts via DuckDuckGo
        url = "https://lite.duckduckgo.com/lite/?q=site:twitter.com+OR+site:x.com+ETH+crypto+when:1d"
        html = _get(url, timeout=10)
        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)

        for s in snippets[:5]:
            text = re.sub(r'<[^>]+>', '', s).strip()
            if len(text) > 20:
                results.append({
                    "content": text[:200],
                    "time": datetime.now(TZ).strftime("%H:%M")
                })
    except:
        pass

    return results


def get_market_sentiment():
    """综合搜索加密市场情绪信号"""
    keywords_list = [
        "ethereum price prediction 2026",
        "crypto market fear greed",
        "SEC crypto regulation news",
        "ETH ETF flow institutional"
    ]

    all_results = []
    for kw in keywords_list[:2]:  # Limit to avoid rate limiting
        results = search_crypto_news(kw, 3)
        all_results.extend(results)

    # Count bullish vs bearish keywords
    bullish = 0
    bearish = 0
    all_text = " ".join(r.get("title", "") + r.get("snippet", "") for r in all_results).lower()

    for word in ["surge", "bullish", "rally", "breakout", "buy", "accumulate",
                 "暴涨", "利好", "反弹", "突破"]:
        bullish += all_text.count(word)
    for word in ["crash", "bearish", "dump", "sell", "outflow", "regulation",
                 "暴跌", "利空", "崩盘", "监管"]:
        bearish += all_text.count(word)

    sentiment = "偏多" if bullish > bearish else "偏空" if bearish > bullish else "中性"

    return {
        "sentiment": sentiment,
        "bullish_signals": bullish,
        "bearish_signals": bearish,
        "articles": len(all_results),
        "top_headlines": [r["title"][:100] for r in all_results[:3]]
    }


# ============================================================
if __name__ == "__main__":
    print("=== 加密新闻 ===")
    news = search_crypto_news()
    for n in news[:5]:
        print(f"  [{n['time']}] {n['title']}")
        if n['snippet']:
            print(f"    {n['snippet'][:100]}")

    print("\n=== 市场情绪 ===")
    sentiment = get_market_sentiment()
    print(f"  方向: {sentiment['sentiment']}")
    print(f"  利多: {sentiment['bullish_signals']} | 利空: {sentiment['bearish_signals']}")
    print(f"  头条: {sentiment['top_headlines']}")
