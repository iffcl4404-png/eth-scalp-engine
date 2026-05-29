"""xAI Grok 集成 — X 推文搜索 + 市场情绪 + 突发新闻"""
import os, urllib.request, json, ssl

API_KEY = os.environ.get("XAI_API_KEY", "")
BASE_URL = "https://api.x.ai/v1"
PROXY = "http://127.0.0.1:7897"


def _call_grok(prompt, system="你是加密货币交易助手，只输出简洁中文分析，不超过200字。"):
    """调用 Grok API"""
    body = json.dumps({
        "model": "grok-4.3",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 400
    }).encode()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(ph)
    req = urllib.request.Request(f"{BASE_URL}/chat/completions", data=body, headers=headers)

    try:
        with opener.open(req, timeout=30) as r:
            data = json.loads(r.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        try:
            # Fallback: direct
            opener2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener2.open(req, timeout=20) as r:
                data = json.loads(r.read())
                return data["choices"][0]["message"]["content"]
        except Exception as e2:
            return f"Grok错误: {e} / {e2}"


def get_crypto_sentiment():
    """获取当前加密市场情绪摘要"""
    return _call_grok(
        "当前ETH价格约$2000，恐惧指数22极度恐惧，PCE通胀3.3%，"
        "伊朗美国正在进行60天停火谈判但最高领袖尚未批准，"
        "美联储6月不降息概率99.4%。"
        "请用3句话分析当前加密市场情绪和短期方向。"
    )


def search_x_crypto(limit=5):
    """搜索 X 上最新的加密/ETH 讨论"""
    return _call_grok(
        f"搜索X/Twitter上最近1小时关于ETH、加密货币的{limit}条最重要讨论或新闻。"
        "按重要性排序，每条格式: [时间] 内容摘要（来源）"
    )


def get_breaking_news():
    """获取最新突发新闻，比金十更快"""
    return _call_grok(
        "搜索最近30分钟内的全球市场突发新闻，"
        "特别关注: 伊朗/中东地缘、美联储讲话、加密监管、美股期货。"
        "用3条以内简洁输出，无新闻就说'暂无突发'。"
    )


def get_trade_advice(price, bias, news_context):
    """Grok 交易建议（第二意见）"""
    return _call_grok(
        f"ETH现价${price}，模型方向{bias}。当前消息面: {news_context}。"
        "作为短线交易顾问，给一个30字以内的建议: 做空/做多/观望？止损放哪？"
    )


# ============================================================
if __name__ == "__main__":
    print("=== 加密情绪 ===")
    print(get_crypto_sentiment())
    print("\n=== X 搜索 ===")
    print(search_x_crypto())
