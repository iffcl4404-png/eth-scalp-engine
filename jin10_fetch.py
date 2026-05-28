"""金十数据抓取 — MCP Streamable HTTP 桥接
用法:
    from jin10_fetch import Jin10
    j10 = Jin10()
    cal = j10.get_calendar()       # 本周财经日历
    flash = j10.get_flash(10)      # 最新10条快讯
    crypto = j10.search_flash("ETH 以太坊 加密货币 比特币")  # 加密相关快讯
    j10.close()
"""
import urllib.request, urllib.error, json, ssl, time, re
from datetime import datetime, timezone, timedelta

TOKEN = "sk-IUx47kZ7t3iebNL5Ar8uK5BZ1oy5Tjul_n4zTAWUgTE"
URL = "https://mcp.jin10.com/mcp"
TZ = timezone(timedelta(hours=8))  # Beijing time
PROXY = "http://127.0.0.1:7897"

class Jin10:
    def __init__(self, proxy=PROXY):
        self.session_id = None
        self._call_id = 0
        ph = urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else urllib.request.ProxyHandler({})
        self._opener = urllib.request.build_opener(ph)
        self._connect()

    def _connect(self):
        """初始化 MCP 会话"""
        try:
            result = self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "eth-monitor", "version": "1.0"}
            })
            self._rpc("notifications/initialized")
            return True
        except Exception as e:
            # Already connected? Try to continue
            return self.session_id is not None

    def _rpc(self, method, params=None):
        """发送 JSON-RPC 请求，自动管理 session ID"""
        self._call_id += 1
        body = {"jsonrpc": "2.0", "method": method}
        if method != "notifications/initialized":
            body["id"] = self._call_id
        if params:
            body["params"] = params

        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        data = json.dumps(body).encode()
        req = urllib.request.Request(URL, data=data, headers=headers, method="POST")

        try:
            with self._opener.open(req, timeout=20) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid
                raw = resp.read().decode("utf-8", errors="replace")
                for line in raw.split("\n"):
                    if line.startswith("data: "):
                        return json.loads(line[6:])
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            if e.code in (202, 204):
                return None
            raise

    def call_tool(self, name, args=None):
        """调用金十 MCP 工具"""
        return self._rpc("tools/call", {"name": name, "arguments": args or {}})

    def get_calendar(self):
        """获取本周财经日历，返回重要事件列表"""
        data = self._parse_tool_result(self.call_tool("list_calendar"))
        return data.get("data", []) if data else []

    def get_flash(self, limit=20):
        """获取最新快讯"""
        data = self._parse_tool_result(self.call_tool("list_flash"))
        if data is None:
            return []
        items = data.get("data", [])
        if isinstance(items, dict):
            items = items.get("items", [])
        return items[:limit] if isinstance(items, list) else []

    def _parse_tool_result(self, result):
        """安全解析工具返回的 JSON，处理截断"""
        if not result or "result" not in result:
            return None
        content = result["result"].get("content", [])
        if not content:
            return None
        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # JSON 可能被截断，尝试修复
            if text.endswith('"') or text.endswith(']') or text.endswith('}'):
                return None
            # 尝试补全
            for suffix in ['"}]}', '"]}', '}]}', '}', ']', '"}']:
                try:
                    return json.loads(text + suffix)
                except json.JSONDecodeError:
                    continue
            return None

    def search_flash(self, keyword, limit=30):
        """搜索快讯"""
        data = self._parse_tool_result(self.call_tool("search_flash", {"keyword": keyword}))
        if data is None:
            return []
        # 支持两种数据格式: {"data": [...]} 或 {"data": {"items": [...]}}
        items = data.get("data", [])
        if isinstance(items, dict):
            items = items.get("items", [])
        return items[:limit] if isinstance(items, list) else []

    def search_news(self, keyword, limit=10):
        """搜索新闻"""
        data = self._parse_tool_result(self.call_tool("search_news", {"keyword": keyword}))
        if data is None:
            return []
        items = data.get("data", [])
        if isinstance(items, dict):
            items = items.get("items", [])
        return items[:limit] if isinstance(items, list) else []

    def get_today_events(self):
        """筛选今天的重大财经事件（1星以上）"""
        cal = self.get_calendar()
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        today_events = []
        for ev in cal:
            pub_time = ev.get("pub_time", "")
            if pub_time.startswith(today) and ev.get("star", 0) >= 1:
                today_events.append({
                    "time": pub_time[11:16] if len(pub_time) >= 16 else pub_time,
                    "title": ev.get("title", ""),
                    "star": ev.get("star", 1),
                    "previous": ev.get("previous", ""),
                    "consensus": ev.get("consensus", ""),
                    "actual": ev.get("actual", ""),
                })
        return today_events

    def get_crypto_impact(self):
        """获取加密市场相关的快讯摘要 — 从 list_flash 中过滤 + 关键词搜索"""
        crypto_keywords = ["比特币", "以太坊", "ETH", "BTC", "加密货币",
                           "加密", "数字资产", "区块链", "合约", "SEC",
                           "CFTC", "ETF", "DeFi", "稳定币", "资金费率",
                           "暴跌", "暴涨", "突破", "崩盘", "监管"]
        all_items = []
        seen = set()

        # 方式1: 从最新快讯中筛选
        latest = self.get_flash(50)
        for f in latest:
            content = f.get("content", "")
            if len(content) < 10:
                continue
            matched = any(kw.lower() in content.lower() for kw in crypto_keywords)
            if not matched:
                continue
            c = content[:200]
            if c not in seen:
                seen.add(c)
                ts = f.get("time", "")
                all_items.append({"time": ts[-8:] if ts else "", "content": c})

        # 方式2: 补充关键词搜索
        for kw in ["比特币", "以太坊", "加密货币"]:
            try:
                flashes = self.search_flash(kw, 5)
            except Exception:
                continue
            for f in flashes:
                c = f.get("content", "")[:200]
                if c not in seen and len(c) > 10:
                    seen.add(c)
                    ts = f.get("time", "")
                    all_items.append({"time": ts[-8:] if ts else "", "content": c})

        all_items.sort(key=lambda x: x["time"], reverse=True)
        return all_items[:20]

    def get_geopolitical_impact(self):
        """获取地缘政治/战争相关快讯（含降温信号）"""
        geo_keywords = ["战争", "冲突", "制裁", "地缘", "导弹", "军事",
                        "中东", "俄乌", "台湾", "南海", "朝鲜", "伊朗",
                        "关税", "贸易战", "脱钩", "封锁",
                        "和谈", "停火", "协议", "备忘录", "降温", "解除制裁"]
        all_items = []
        seen = set()

        # 从快讯中筛选
        latest = self.get_flash(50)
        for f in latest:
            content = f.get("content", "")
            if len(content) < 10: continue
            matched = any(kw in content for kw in geo_keywords)
            if not matched: continue
            c = content[:200]
            if c not in seen:
                seen.add(c)
                ts = f.get("time", "")[-8:] if f.get("time") else ""
                all_items.append({"time": ts, "content": c})

        # 补充搜索
        for kw in ["地缘政治", "战争", "关税", "制裁"]:
            try:
                for f in self.search_flash(kw, 3):
                    c = f.get("content", "")[:200]
                    if c not in seen and len(c) > 10:
                        seen.add(c)
                        ts = f.get("time", "")[-8:] if f.get("time") else ""
                        all_items.append({"time": ts, "content": c})
            except: continue

        all_items.sort(key=lambda x: x["time"], reverse=True)
        return all_items[:15]

    def get_macro_impact(self):
        """获取宏观经济/央行政策相关快讯"""
        macro_keywords = ["央行", "加息", "降息", "利率", "通胀", "CPI",
                          "GDP", "非农", "美联储", "欧央行", "日本央行",
                          "衰退", "PMI", "就业", "失业", "国债收益率"]
        all_items = []
        seen = set()

        # 从快讯中筛选
        latest = self.get_flash(50)
        for f in latest:
            content = f.get("content", "")
            if len(content) < 10: continue
            matched = any(kw in content for kw in macro_keywords)
            if not matched: continue
            c = content[:200]
            if c not in seen:
                seen.add(c)
                ts = f.get("time", "")[-8:] if f.get("time") else ""
                all_items.append({"time": ts, "content": c})

        # 补充搜索
        for kw in ["美联储", "央行", "利率"]:
            try:
                for f in self.search_flash(kw, 3):
                    c = f.get("content", "")[:200]
                    if c not in seen and len(c) > 10:
                        seen.add(c)
                        ts = f.get("time", "")[-8:] if f.get("time") else ""
                        all_items.append({"time": ts, "content": c})
            except: continue

        all_items.sort(key=lambda x: x["time"], reverse=True)
        return all_items[:15]

    def get_all_impact(self):
        """一次调用获取所有维度的快讯摘要"""
        return {
            "crypto": self.get_crypto_impact(),
            "geopolitical": self.get_geopolitical_impact(),
            "macro": self.get_macro_impact(),
            "calendar": self.get_today_events(),
        }

    def close(self):
        """会话由服务端管理，无需显式关闭"""
        self.session_id = None


def format_for_report(j10, existing_c6_text=""):
    """生成 eth-monitor 用的金十数据摘要"""
    parts = []

    # 今日经济事件
    events = j10.get_today_events()
    high_impact = [e for e in events if e["star"] >= 3]
    if high_impact:
        titles = "、".join(e["title"][:20] for e in high_impact[:3])
        parts.append(f"今日重磅: {titles}")
    elif events:
        titles = "、".join(e["title"][:20] for e in events[:2])
        parts.append(f"今日事件: {titles}")
    else:
        parts.append("今日无重大数据")

    # 加密相关快讯
    crypto = j10.get_crypto_impact()
    if crypto:
        # 取前3条关键信息
        key_words = ["ETH", "以太坊", "比特币", "SEC", "监管", "暴跌", "暴涨", "ETF"]
        important = [c for c in crypto if any(kw in c["content"] for kw in key_words)]
        highlights = important[:2] if important else crypto[:1]
        for h in highlights:
            parts.append(f"快讯: {h['content'][:80]}")

    return " | ".join(parts)


# === 单文件测试 ===
if __name__ == "__main__":
    j10 = Jin10()
    print("=== 今日财经事件 ===")
    events = j10.get_today_events()
    for e in events[:10]:
        stars = "★" * e["star"]
        print(f"  {e['time']} {stars} {e['title']}")
        if e.get("previous"):
            print(f"    前值:{e['previous']} 预期:{e['consensus']} 公布:{e['actual']}")

    print(f"\n=== 加密快讯 ({len(crypto := j10.get_crypto_impact())}条) ===")
    for c in crypto[:10]:
        print(f"  {c['time']} {c['content']}")

    print("\n=== 报告摘要 ===")
    print(format_for_report(j10))
    j10.close()
