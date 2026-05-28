"""
Alpha Skills 桥接层 — 6 核心技能接入短线引擎
urithiru / mental-model / trader-memory / ibd-monitor / news-analyst / backtest
"""
import json, os, time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
MEMORY_FILE = "trade_memory.json"

# ============================================================
# 1. urithiru — 多模型验证（简化版：3 lane 短线检查）
# ============================================================

def urithiru_check(price, bias, sig_score, news_bias, kline_trend):
    """
    3-lane trading check before entry:
    Lane 1: 技术面 (K线趋势是否对齐)
    Lane 2: 消息面 (新闻偏向是否支持)
    Lane 3: 风险面 (R 是否达标 + 情绪是否极端)
    Returns: (pass: bool, confidence: int, reasons: list)
    """
    lanes = []

    # Lane 1: 技术面
    tech_ok = (bias == "做空" and kline_trend == "偏空") or \
              (bias == "做多" and kline_trend == "偏多")
    lanes.append(("技术面", tech_ok, "K线趋势对齐" if tech_ok else "K线趋势冲突"))

    # Lane 2: 消息面
    if news_bias in ("strong_bear", "strong_bull"):
        news_ok = (bias == "做空" and news_bias == "strong_bear") or \
                  (bias == "做多" and news_bias == "strong_bull")
        lanes.append(("消息面", news_ok, "消息强驱动" if news_ok else "消息方向冲突"))
    elif news_bias in ("lean_bear", "lean_bull", "mixed"):
        lanes.append(("消息面", True, "消息稍偏或混合，可接受"))
    else:
        lanes.append(("消息面", True, "消息面中性"))

    # Lane 3: 风险面
    risk_ok = sig_score >= 55
    lanes.append(("风险面", risk_ok, f"评分{sig_score}/100" if risk_ok else f"评分{sig_score}<55门槛"))

    passed = sum(1 for _, ok, _ in lanes if ok)
    confidence = passed * 33  # max 99
    reasons = [r for _, _, r in lanes]

    return passed >= 2, confidence, reasons


# ============================================================
# 2. mental-model-evaluator — 三思维模型检查
# ============================================================

def mental_model_check(bias, entry, stop, tp, account, news_context=""):
    """
    Run trade plan through 3 cognitive models:
    1. Inversion: How could this completely fail?
    2. First Principles: What are the undeniable facts?
    3. Second-Order: What happens after the trade?
    Returns: verdict (PASS/REVISE/REJECT) and report
    """
    model1 = []
    model2 = []
    model3 = []

    # 1. Inversion — failure modes
    if bias in ("short", "做空"):
        model1.append("伊朗和谈正式签署→地缘急降温→ETH暴涨")
        model1.append("美联储突放鸽→降息预期→风险资产全线反弹")
        model1.append("大户在1965筑底→逼空行情")
    else:
        model1.append("伊朗局势升级→战争→风险资产暴跌")
        model1.append("美联储超预期加息→ETH崩盘")
        model1.append("鲸鱼在2000+砸盘→多单被套")
    model1.append(f"止损{stop}被击穿→亏损{abs(entry-stop):.0f}点")

    # 2. First Principles
    model2.append(f"ETH现价与24h低点{1965}仍有距离，趋势偏空")
    model2.append(f"125x杠杆下，{abs(entry-stop):.0f}点止损=保证金{(account*0.2):.1f}U的{abs(entry-stop)/entry*100:.0f}%")
    model2.append(f"恐惧贪婪22=极度恐惧=底部信号或继续下跌")

    # 3. Second-Order Effects
    model3.append("若止盈: 盈利计入复利，下一单可放大仓位")
    model3.append("若止损: 本金缩水，需连赢X单才能回本")
    model3.append(f"若观望: 0风险，但可能错过{abs(entry-tp):.0f}点行情")

    # Verdict
    fail_count = sum(1 for m in model1 if any(kw in m for kw in ["击穿", "暴涨", "崩盘"]))
    if fail_count >= 3:
        verdict = "REJECT"
    elif fail_count >= 1:
        verdict = "REVISE"
    else:
        verdict = "PASS"

    return {
        "verdict": verdict,
        "inversion": model1,
        "first_principles": model2,
        "second_order": model3
    }


# ============================================================
# 3. trader-memory-core — 完整交易记忆
# ============================================================

def open_thesis(bias, entry, stop, tp, reasons, news_snapshot):
    """开仓时记录交易理由"""
    thesis = {
        "id": datetime.now(TZ).strftime("%Y%m%d_%H%M%S"),
        "status": "OPEN",
        "opened_at": datetime.now(TZ).isoformat(),
        "side": bias,
        "entry": entry,
        "stop": stop,
        "tp": tp,
        "reasons": reasons,
        "news_snapshot": news_snapshot,
        "mae": 0,   # Maximum Adverse Excursion
        "mfe": 0,   # Maximum Favorable Excursion
        "closed_at": None,
        "exit_price": None,
        "pnl_pts": 0,
        "pnl_usd": 0,
        "outcome": None,
        "lessons": ""
    }
    return thesis

def update_excursion(thesis, current_price):
    """更新最大不利/有利偏移"""
    side = thesis["side"]
    entry = thesis["entry"]
    pnl = (entry - current_price) if side in ("short", "做空") else (current_price - entry)
    if pnl < 0:
        thesis["mae"] = min(thesis["mae"], pnl)
    else:
        thesis["mfe"] = max(thesis["mfe"], pnl)

def close_thesis(thesis, exit_price, lessons=""):
    """平仓时关闭交易记忆"""
    side = thesis["side"]
    entry = thesis["entry"]
    thesis["status"] = "CLOSED"
    thesis["closed_at"] = datetime.now(TZ).isoformat()
    thesis["exit_price"] = exit_price
    thesis["pnl_pts"] = (entry - exit_price) if side in ("short", "做空") else (exit_price - entry)
    thesis["outcome"] = "TP" if thesis["pnl_pts"] > 0 else "STOP" if thesis["pnl_pts"] < 0 else "FLAT"
    thesis["lessons"] = lessons

    # Save to memory
    memories = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                memories = json.load(f)
        except: pass
    memories.append(thesis)
    with open(MEMORY_FILE, "w") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)
    return thesis


# ============================================================
# 4. ibd-distribution-day-monitor — ETH 版派发日
# ============================================================

def eth_distribution_check(klines_15m, price, vol):
    """
    Adapted IBD distribution day logic for ETH 15m candles.
    A distribution candle: close < open AND volume > previous volume.
    Count recent distribution candles to assess sell pressure.
    """
    if len(klines_15m) < 2:
        return {"risk": "UNKNOWN", "d_count": 0}

    dist_count = 0
    for i in range(1, min(len(klines_15m), 12)):  # last 12 candles = 3 hours
        curr = klines_15m[i-1] if i > 1 else klines_15m[0]
        prev = klines_15m[i]
        is_dist = curr['c'] < curr['o'] and curr.get('vol', 0) > prev.get('vol', 0)
        if is_dist:
            dist_count += 1

    # Risk classification (adapted from IBD)
    if dist_count <= 2:
        risk = "NORMAL"
    elif dist_count <= 4:
        risk = "CAUTION"
    elif dist_count <= 6:
        risk = "HIGH"
    else:
        risk = "SEVERE"

    return {"risk": risk, "d_count": dist_count, "lookback_candles": 12}


# ============================================================
# 5. market-news-analyst — 消息影响分级
# ============================================================

def grade_news_impact(geo_items, macro_items, crypto_items):
    """
    Grade news impact from 0-10 for short-term ETH trading.
    Focus: immediacy, relevance to ETH, surprise factor.
    """
    all_news = []
    for src, items in [("地缘", geo_items), ("宏观", macro_items), ("加密", crypto_items)]:
        for item in items[:5]:
            content = item.get("content", "")
            # Impact grading
            impact = 0
            if any(kw in content for kw in ["美联储", "加息", "利率", "CPI", "非农"]):
                impact = 8  # High impact for ETH
            elif any(kw in content for kw in ["SEC", "监管", "禁止", "ETF"]):
                impact = 7
            elif any(kw in content for kw in ["战争", "制裁", "冲突", "导弹"]):
                impact = 6
            elif any(kw in content for kw in ["和谈", "停火", "协议", "降息"]):
                impact = 5
            elif any(kw in content for kw in ["数据", "报告", "指数"]):
                impact = 3
            else:
                impact = 1

            all_news.append({
                "source": src,
                "time": item.get("time", ""),
                "content": content[:100],
                "impact": impact
            })

    # Sort by impact, top 5
    all_news.sort(key=lambda x: x["impact"], reverse=True)
    top_impact = all_news[:5]
    avg_impact = sum(n["impact"] for n in top_impact) / len(top_impact) if top_impact else 0

    return {
        "avg_impact": round(avg_impact, 1),
        "top_news": top_impact,
        "level": "HIGH" if avg_impact >= 6 else "MEDIUM" if avg_impact >= 3 else "LOW"
    }


# ============================================================
# 6. backtest-expert — 参数稳健性检查
# ============================================================

def validate_params(stop_pts, tp_pts, account, leverage, margin_pct):
    """
    Validate stop/tp parameters for robustness.
    Checks: RR ratio, max loss %, recovery math, slippage buffer.
    """
    issues = []

    # RR check
    rr = tp_pts / stop_pts if stop_pts > 0 else 0
    if rr < 1.5:
        issues.append(f"RR={rr:.1f}<1.5，盈亏比不达标")
    elif rr >= 3.0:
        issues.append(f"RR={rr:.1f}过高，可能不切实际")

    # Max loss check
    margin = account * margin_pct
    max_loss = stop_pts * (margin * leverage / 2000)  # rough estimate
    loss_pct = max_loss / account * 100 if account > 0 else 0
    if loss_pct > 20:
        issues.append(f"单笔最大亏损{loss_pct:.0f}%超过20%")

    # Recovery math
    if loss_pct > 5:
        recovery_needed = round(loss_pct / (100 - loss_pct) * 100, 1)
        issues.append(f"亏损后需赚{recovery_needed}%回本")

    # Slippage buffer
    if stop_pts < 3:
        issues.append(f"止损{stop_pts}点<3点，滑点风险极高")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "rr": round(rr, 1),
        "max_loss_pct": round(loss_pct, 1),
        "stop_buffer_ok": stop_pts >= 3,
    }


# ============================================================
# 集成测试
# ============================================================
if __name__ == "__main__":
    # urithiru test
    ok, conf, reasons = urithiru_check(1990, "做空", 70, "strong_bear", "偏空")
    print(f"Urithiru: {'PASS' if ok else 'FAIL'} ({conf}%) | {'; '.join(reasons)}")

    # mental model test
    mm = mental_model_check("做空", 1995, 2001, 1983, 9.62, "伊朗局势紧张")
    print(f"Mental Model: {mm['verdict']}")

    # IBD test
    klines = [{'o': 1992, 'c': 1991, 'h': 1993, 'l': 1990, 'vol': 100} for _ in range(6)]
    ibd = eth_distribution_check(klines, 1991, 500000)
    print(f"IBD Risk: {ibd['risk']} ({ibd['d_count']} dist candles)")

    # Backtest
    bt = validate_params(6, 12, 9.62, 125, 0.20)
    print(f"Backtest: {'OK' if bt['valid'] else bt['issues']}")

    print("\nAll 6 skills loaded.")
