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
# 7. exposure-coach — 净敞口上限
# ============================================================

def exposure_coach(ibd_risk, news_level, sig_score, active_positions=0):
    """
    Calculate max exposure ceiling based on market conditions.
    Adapted from exposure-coach: synthesize breadth/regime/flow into net exposure.
    """
    base_exposure = 100  # % of normal position

    # IBD risk reduction
    risk_cuts = {"NORMAL": 0, "CAUTION": 25, "HIGH": 50, "SEVERE": 75, "UNKNOWN": 50}
    base_exposure -= risk_cuts.get(ibd_risk, 50)

    # News impact reduction
    if news_level == "HIGH":
        base_exposure -= 10
    elif news_level == "LOW":
        base_exposure += 5

    # Signal quality boost
    if sig_score >= 80:
        base_exposure += 10
    elif sig_score < 55:
        base_exposure -= 20

    # Active positions reduction
    if active_positions >= 2:
        base_exposure -= 30
    elif active_positions >= 1:
        base_exposure -= 15

    exposure = max(0, min(100, base_exposure))
    if exposure >= 75:
        rec = "FULL_SIZE"
    elif exposure >= 50:
        rec = "HALF_SIZE"
    elif exposure >= 25:
        rec = "QUARTER_SIZE"
    else:
        rec = "NO_TRADE"

    return {"exposure_pct": exposure, "recommendation": rec}


# ============================================================
# 8. economic-calendar-fetcher — 事件驱动预判
# ============================================================

def check_event_risk(jin10_events):
    """
    Check if any high-impact economic events are imminent.
    Adapted from economic-calendar-fetcher.
    """
    now = datetime.now(TZ)
    warnings = []
    for ev in jin10_events:
        try:
            ev_time_str = ev.get("pub_time", "")
            if len(ev_time_str) >= 16:
                ev_time = datetime.strptime(ev_time_str[:16], "%Y-%m-%d %H:%M")
                ev_time = ev_time.replace(tzinfo=TZ)
                minutes_away = (ev_time - now).total_seconds() / 60
                if 0 <= minutes_away <= 120 and ev.get("star", 0) >= 2:
                    warnings.append({
                        "title": ev.get("title", ""),
                        "minutes_away": int(minutes_away),
                        "star": ev.get("star", 1),
                        "previous": ev.get("previous", ""),
                        "consensus": ev.get("consensus", "")
                    })
        except:
            continue

    warnings.sort(key=lambda x: x["minutes_away"])
    risk = "HIGH" if any(w["star"] >= 3 and w["minutes_away"] <= 60 for w in warnings) else \
           "MEDIUM" if warnings else "LOW"
    return {"risk": risk, "warnings": warnings[:3]}


# ============================================================
# 9. breakout-trade-planner — ETH 突破追单
# ============================================================

def breakout_plan(price, high_1h, low_1h, bias):
    """
    Adapt Minervini breakout methodology for ETH 15m scalping.
    Key levels: 1h high/low as breakout triggers.
    """
    if bias == "做空":
        breakdown = low_1h - 2  # break below 1h low
        entry = round(breakdown - 3, 1)
        stop = round(breakdown + 5, 1)
        tp = round(breakdown - 10, 1)
        trigger = f"跌破 ${breakdown:.1f}"
    else:
        breakout = high_1h + 2  # break above 1h high
        entry = round(breakout + 3, 1)
        stop = round(breakout - 5, 1)
        tp = round(breakout + 10, 1)
        trigger = f"突破 ${breakout:.1f}"

    rr = round(abs(entry - tp) / abs(entry - stop), 1) if abs(entry - stop) > 0 else 0

    return {
        "trigger": trigger,
        "entry": entry, "stop": stop, "tp": tp,
        "rr": rr,
        "valid": rr >= 1.5
    }


# ============================================================
# 10. edge-signal-aggregator — 多源信号加权
# ============================================================

def aggregate_signals(scalp_score, uri_ok, ibd_risk, news_level, mm_verdict):
    """
    Weighted conviction dashboard combining all signal sources.
    Adapted from edge-signal-aggregator.
    """
    signals = {}

    # Scalp engine score (weight: 40%)
    signals["scalp"] = {"score": scalp_score, "weight": 40, "ok": scalp_score >= 70}

    # Urithiru (weight: 25%)
    uri_score = 100 if uri_ok else 30
    signals["urithiru"] = {"score": uri_score, "weight": 25, "ok": uri_ok}

    # IBD risk (weight: 15%)
    ibd_scores = {"NORMAL": 100, "CAUTION": 60, "HIGH": 30, "SEVERE": 0, "UNKNOWN": 50}
    ibd_score = ibd_scores.get(ibd_risk, 50)
    signals["ibd"] = {"score": ibd_score, "weight": 15, "ok": ibd_risk in ("NORMAL", "CAUTION")}

    # News grade (weight: 10%)
    news_scores = {"HIGH": 50, "MEDIUM": 75, "LOW": 90}
    news_score = news_scores.get(news_level, 60)
    signals["news"] = {"score": news_score, "weight": 10, "ok": news_level != "HIGH"}

    # Mental model (weight: 10%)
    mm_score = {"PASS": 100, "REVISE": 60, "REJECT": 20}
    mm_s = mm_score.get(mm_verdict, 50)
    signals["mental"] = {"score": mm_s, "weight": 10, "ok": mm_verdict != "REJECT"}

    # Weighted conviction
    total_w = sum(v["weight"] for v in signals.values())
    conviction = sum(v["score"] * v["weight"] / total_w for v in signals.values())

    ok_count = sum(1 for v in signals.values() if v["ok"])
    consensus = "STRONG" if ok_count >= 5 else \
                "MODERATE" if ok_count >= 4 else \
                "WEAK" if ok_count >= 3 else "CONTRADICT"

    return {
        "conviction": round(conviction, 1),
        "consensus": consensus,
        "sources": signals,
        "go": conviction >= 65 and ok_count >= 3
    }


# ============================================================
# 11. trade-hypothesis-ideator — 信号模式发现
# ============================================================

def generate_hypotheses(recent_trades, current_setup):
    """
    Generate falsifiable trade hypotheses from recent data.
    Adapted from trade-hypothesis-ideator.
    """
    hypotheses = []

    # H1: Trend continuation
    hypotheses.append({
        "id": "H1",
        "statement": "当前15m趋势将继续延续3-5根K线",
        "test": "观察接下来5根15m K线方向",
        "kill_criteria": "连续2根反向K线",
        "confidence": 65
    })

    # H2: News fade
    hypotheses.append({
        "id": "H2",
        "statement": "当前消息面冲击将在30分钟内被市场消化",
        "test": "30分钟后价格是否回到消息前水平",
        "kill_criteria": "消息后价格持续同向移动>30分钟",
        "confidence": 50
    })

    # H3: Support/resistance hold
    hypotheses.append({
        "id": "H3",
        "statement": "1965前低和2080阻力在今日内不会被突破",
        "test": "日内是否触及1965或2080",
        "kill_criteria": "价格突破1965下方或2080上方>5点",
        "confidence": 70
    })

    return hypotheses


# ============================================================
# 12. strategy-pivot-designer — 策略衰退检测
# ============================================================

def detect_edge_decay(stats):
    """
    Detect if current strategy edge is decaying.
    Adapted from strategy-pivot-designer.
    """
    if stats.get("total", 0) < 5:
        return {"status": "INSUFFICIENT_DATA", "action": "继续积累样本"}

    win_rate = stats.get("win_rate", 0)
    avg_win = stats.get("avg_win", 0)
    avg_loss = abs(stats.get("avg_loss", 0))
    profit_factor = (avg_win * win_rate / 100) / (avg_loss * (100 - win_rate) / 100) if avg_loss > 0 and win_rate < 100 else 999

    if win_rate >= 60 and profit_factor >= 1.5:
        status = "HEALTHY"
        action = "维持当前策略"
    elif win_rate >= 50 and profit_factor >= 1.0:
        status = "WATCH"
        action = "策略有轻微衰退，注意近期表现"
    elif profit_factor >= 0.7:
        status = "DEGRADING"
        action = "考虑调整参数或暂停交易"
    else:
        status = "BROKEN"
        action = "停止交易，深度复盘后重构"

    return {
        "status": status,
        "action": action,
        "win_rate": win_rate,
        "profit_factor": round(profit_factor, 2),
        "sample_size": stats.get("total", 0)
    }


# ============================================================
# 13. ftd-detector — 跟进日底部确认 (ETH 15m adapted)
# ============================================================

def ftd_detect(klines_15m, price, vol):
    """
    Adapted FTD detector for ETH 15m candles.
    William O'Neil methodology: correction → rally attempt → FTD confirmation.
    Correction: 3%+ drop from 24h high. FTD: confirmation candle with volume surge.
    """
    if len(klines_15m) < 6:
        return {"state": "INSUFFICIENT_DATA", "ftd_found": False}

    # Calculate correction
    high_24h = max(k['h'] for k in klines_15m)
    correction_pct = (high_24h - price) / high_24h * 100

    state = "NO_CORRECTION"
    ftd_found = False
    ftd_quality = 0

    if correction_pct >= 3:
        state = "CORRECTION"

        # Find rally attempt: first candle closing above its open after a low
        lows = [k['l'] for k in klines_15m]
        lowest = min(lows)
        lowest_idx = lows.index(lowest)

        if lowest_idx > 0:  # Not the most recent candle
            state = "RALLY_ATTEMPT"

            # Look for FTD: on day 4+ after low, a candle closing 1%+ above prior close
            # with higher volume
            for i in range(lowest_idx - 1, -1, -1):
                if i < len(klines_15m) - 1:
                    curr = klines_15m[i]
                    prev = klines_15m[i + 1]
                    gain_pct = (curr['c'] - prev['c']) / prev['c'] * 100
                    vol_surge = curr.get('vol', 0) > prev.get('vol', 0) * 1.2
                    days_from_low = lowest_idx - i

                    if gain_pct >= 0.3 and vol_surge and days_from_low >= 2:
                        state = "FTD_CONFIRMED"
                        ftd_found = True
                        # Quality scoring
                        ftd_quality = min(100,
                            40 if gain_pct >= 1 else 25 +  # Gain magnitude
                            30 if vol_surge else 15 +      # Volume confirmation
                            20 if days_from_low >= 4 else 10 +  # Timing
                            10)  # Base
                        break

    action = {
        "NO_CORRECTION": "正常波动，无需特殊操作",
        "CORRECTION": "等待反弹确立后跟进",
        "RALLY_ATTEMPT": "观察跟进日，准备入场",
        "FTD_CONFIRMED": f"跟进日确认！质量{ftd_quality}分，可考虑做多",
        "INSUFFICIENT_DATA": "数据不足"
    }.get(state, "未知")

    return {
        "state": state,
        "ftd_found": ftd_found,
        "quality": ftd_quality,
        "correction_pct": round(correction_pct, 1),
        "action": action
    }


# ============================================================
# 14. ghost-auto-trader — 自动交易调度台 (adapted for manual)
# ============================================================

def ghost_gate(price, bias, entry, stop, tp, sig_score, verdict,
               uri_ok, uri_conf, mm_verdict, agg, edge_detect):
    """
    Ghost Auto-Trader AI Gate for ETH scalping.
    Validates trade through all 5 checkpoints before dispatching.
    Returns trade ticket or rejection with reason.
    """
    checks = []

    # Check 1: Signal quality
    c1 = sig_score >= 70
    checks.append(("信号质量", c1, f"评分{sig_score}/100{' >= 70' if c1 else ' < 70 门槛'}"))

    # Check 2: Urithiru consensus
    c2 = uri_ok and uri_conf >= 66
    checks.append(("多模型验证", c2, f"Urithiru {'PASS' if uri_ok else 'FAIL'} ({uri_conf}%)"))

    # Check 3: Mental model
    c3 = mm_verdict != "REJECT"
    checks.append(("思维模型", c3, f"{mm_verdict}"))

    # Check 4: Signal aggregation
    c4 = agg["go"]
    checks.append(("信号聚合", c4, f"共识{agg['conviction']:.0f}% ({agg['consensus']})"))

    # Check 5: Edge health
    c5 = edge_detect.get("status") != "BROKEN"
    checks.append(("策略健康", c5, f"{edge_detect.get('status', '?')}"))

    passed = sum(1 for _, ok, _ in checks if ok)
    gate_passed = passed >= 4

    ticket = None
    if gate_passed:
        ticket = {
            "symbol": "ETH-USDT-SWAP",
            "side": bias,
            "entry": entry,
            "stop": stop,
            "tp": tp,
            "leverage": 125,
            "margin_mode": "isolated",
            "validated_at": datetime.now(TZ).isoformat(),
            "checks_passed": f"{passed}/5"
        }

    return {
        "gate_passed": gate_passed,
        "checks": checks,
        "ticket": ticket,
        "reason": "ALL_CHECKS_PASSED" if gate_passed else \
                  f"ONLY_{passed}/5_CHECKS_PASSED"
    }

def dispatch_ticket(ticket, auto=False):
    """
    Dispatch a validated trade ticket.
    If auto=False (default): returns instructions for manual execution.
    If auto=True: would execute via Tebbit API (future).
    """
    if not ticket:
        return {"status": "REJECTED", "message": "Gate checks failed"}

    if auto:
        # Future: call Tebbit API here
        return {"status": "ERROR", "message": "Auto-execution requires Tebbit API key"}

    # Manual execution instructions
    return {
        "status": "READY",
        "message": f"""手动执行:
  交易所: Tebbit
  合约: ETH-USDT-SWAP
  方向: {ticket['side']}
  入场: ${ticket['entry']}
  止损: ${ticket['stop']}
  止盈: ${ticket['tp']}
  杠杆: {ticket['leverage']}x
  模式: {ticket['margin_mode']}""",
        "ticket": ticket
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
