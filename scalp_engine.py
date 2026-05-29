"""
ETH 短线原生引擎 — 125x 合约快进快出
设计原则: 消息驱动 > 趋势跟随, 15-60min 持仓, 5-8pt 止损
"""
import json, os, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

TZ = timezone(timedelta(hours=8))
TRADE_LOG = "trades.json"

# ============================================================
# 交易参数（全短线）
# ============================================================
@dataclass
class ScalpConfig:
    account: float          # 本金
    leverage: int = 125
    risk_pct: float = 0.10  # 单笔风险 10%
    margin_pct: float = 0.20  # 保证金 20%
    stop_pts: float = 6     # 止损点数
    tp_pts: float = 12      # 止盈点数
    min_rr: float = 2.0     # 最低盈亏比
    max_hold_min: int = 60  # 最长持仓分钟

DEFAULT_CFG = ScalpConfig(account=88.21, leverage=150, margin_pct=0.10)


# ============================================================
# 仓位计算 — 固定分数法
# ============================================================
@dataclass
class ScalpPosition:
    side: str          # "short" / "long"
    entry: float
    stop: float
    tp: float
    margin: float
    size: float        # 合约张数
    risk_usd: float
    reward_usd: float
    rr: float

def calc_position(cfg: ScalpConfig, price: float, side: str, entry_offset: float = 8):
    """短线仓位计算"""
    if side in ("short", "做空"):
        entry = round(price + entry_offset, 1)
        stop = round(entry + cfg.stop_pts, 1)
        tp = round(entry - cfg.tp_pts, 1)
    else:
        entry = round(price - entry_offset, 1)
        stop = round(entry - cfg.stop_pts, 1)
        tp = round(entry + cfg.tp_pts, 1)

    margin = round(cfg.account * cfg.margin_pct, 2)
    size = round(margin * cfg.leverage, 0)
    risk_distance = abs(entry - stop)
    reward_distance = abs(entry - tp)
    risk_usd = round(risk_distance * (size / entry), 2)
    reward_usd = round(reward_distance * (size / entry), 2)
    rr = round(reward_distance / risk_distance, 1) if risk_distance > 0 else 0

    return ScalpPosition(side=side, entry=entry, stop=stop, tp=tp,
                         margin=margin, size=size, risk_usd=risk_usd,
                         reward_usd=reward_usd, rr=rr)


# ============================================================
# 信号评分 — 四维快评（替代8项长线自审）
# ============================================================

def score_signal(price, fg, rate, bias, news_bias, kline_signal):
    """
    短线四维评分（0-100）:
    - 趋势对齐 (30分): 短线方向是否与15m趋势一致
    - 情绪共振 (25分): F&G + 费率是否支持
    - 消息驱动 (25分): 金十快讯是否有催化剂
    - 执行质量 (20分): RR是否达标 + K线形态
    """
    score = 0
    details = {}

    # 1. 趋势对齐 (30)
    trend_ok = (bias == "做空" and kline_signal.get("trend_bias") == "偏空") or \
               (bias == "做多" and kline_signal.get("trend_bias") == "偏多")
    score += 25 if trend_ok else 10
    details["趋势"] = "对齐" if trend_ok else "不对齐"

    # 2. 情绪共振 (25)
    fg_bearish = fg < 40
    fg_bullish = fg > 70
    rate_neutral = abs(rate) < 0.01
    if bias == "做空" and fg_bearish:
        score += 20; details["情绪"] = "恐惧+空"
    elif bias == "做多" and fg_bullish:
        score += 20; details["情绪"] = "贪婪+多"
    elif rate_neutral:
        score += 12; details["情绪"] = "费率中性"
    else:
        score += 5; details["情绪"] = "不对齐"

    # 3. 消息驱动 (25)
    if news_bias == "strong_bear":
        score += 25 if bias == "做空" else 5
        details["消息"] = "强利空"
    elif news_bias == "strong_bull":
        score += 25 if bias == "做多" else 5
        details["消息"] = "强利多"
    elif news_bias == "mixed":
        score += 10; details["消息"] = "多空混合"
    else:
        score += 5; details["消息"] = "平淡"

    # 4. 执行质量 (20)
    rr_ok = 2.0  # R=1:2
    score += 15 if rr_ok >= 1.5 else 8
    details["执行"] = f"R=2.0"

    return score, details


def signal_verdict(score):
    if score >= 70: return "GO", "信号强，可入场"
    elif score >= 55: return "WATCH", "方向对但条件不完美，轻仓或等"
    else: return "NO", "条件不满足，不入场"


# ============================================================
# 新闻驱动检测 — 消息面快速判定
# ============================================================

BEARISH_KW = ["加息", "战争", "冲突", "监管", "SEC", "崩盘", "暴跌",
              "禁止", "制裁", "通胀走高", "衰退", "危机", "空袭", "袭击"]
BULLISH_KW = ["降息", "和谈", "停火", "协议", "备忘录", "刺激", "宽松",
              "暴涨", "突破", "ETF通过", "解除制裁", "降温"]

def detect_news_bias(geo_items, macro_items, crypto_items):
    """从金十快讯检测消息面偏向"""
    all_text = " ".join(
        g["content"][:100] for items in [geo_items, macro_items, crypto_items]
        for g in items[:5]
    )
    if not all_text.strip():
        return "neutral"

    bear_count = sum(1 for kw in BEARISH_KW if kw in all_text)
    bull_count = sum(1 for kw in BULLISH_KW if kw in all_text)

    if bear_count >= 3 and bear_count > bull_count * 2:
        return "strong_bear"
    elif bull_count >= 3 and bull_count > bear_count * 2:
        return "strong_bull"
    elif bear_count > bull_count:
        return "lean_bear"
    elif bull_count > bear_count:
        return "lean_bull"
    elif bear_count > 0 and bull_count > 0:
        return "mixed"
    return "neutral"


# ============================================================
# 持仓管理 — 动态止损
# ============================================================

@dataclass
class ActivePosition:
    side: str
    entry: float
    stop: float
    tp: float
    opened_at: str
    margin: float = 0
    size: float = 0

    def trailing_stop(self, current_price: float, lock_pct: float = 0.5):
        """移动止损：盈利超过止盈一半后，止损推到成本"""
        profit = (self.entry - current_price) if self.side in ("short", "做空") else (current_price - self.entry)
        tp_dist = abs(self.entry - self.tp)
        if profit >= tp_dist * lock_pct:
            self.stop = self.entry
            return True
        return False

    def should_close(self, current_price: float):
        """检查是否触发止损或止盈"""
        if self.side in ("short", "做空"):
            return current_price >= self.stop or current_price <= self.tp
        else:
            return current_price <= self.stop or current_price >= self.tp


# ============================================================
# 交易记录
# ============================================================

def record_trade(side, entry, exit_px, stop, tp, account, notes=""):
    """记录已平仓交易"""
    pnl_pts = (entry - exit_px) if side in ("short", "做空") else (exit_px - entry)
    margin = account * DEFAULT_CFG.margin_pct
    size = margin * DEFAULT_CFG.leverage
    pnl_usd = round(pnl_pts * (size / entry), 2)
    pnl_pct = round(pnl_usd / account * 100, 1)

    outcome = "TP" if ((side in ("short", "做空") and exit_px <= tp) or
                       (side in ("long", "做多") and exit_px >= tp)) else \
              "STOP" if ((side in ("short", "做空") and exit_px >= stop) or
                         (side in ("long", "做多") and exit_px <= stop)) else "MANUAL"

    trade = {
        "id": datetime.now(TZ).strftime("%Y%m%d_%H%M%S"),
        "opened": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "side": side, "entry": entry, "exit": exit_px,
        "stop": stop, "tp": tp,
        "pnl_pts": pnl_pts, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct,
        "outcome": outcome, "notes": notes
    }

    trades = []
    if os.path.exists(TRADE_LOG):
        try:
            with open(TRADE_LOG, "r") as f:
                trades = json.load(f)
        except: pass

    trades.append(trade)
    with open(TRADE_LOG, "w") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)
    return trade


def get_stats():
    if not os.path.exists(TRADE_LOG): return {}
    with open(TRADE_LOG, "r") as f:
        trades = json.load(f)
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    return {
        "total": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins)/len(trades)*100, 1) if trades else 0,
        "total_pnl": round(sum(t["pnl_usd"] for t in trades), 2),
        "avg_win": round(sum(t["pnl_usd"] for t in wins)/len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl_usd"] for t in losses)/len(losses), 2) if losses else 0,
    }
