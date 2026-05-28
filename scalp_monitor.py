"""
ETH 短线监控 — 消息驱动 + 15分钟级别
用法: python scalp_monitor.py
输出: ~/Desktop/scalp-report.txt
"""
import urllib.request, json, os, sys, ssl
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scalp_engine import (
    DEFAULT_CFG, ScalpConfig, calc_position,
    score_signal, signal_verdict, detect_news_bias,
    ActivePosition, record_trade, get_stats
)
from scalp_skills import (
    urithiru_check, mental_model_check, eth_distribution_check,
    grade_news_impact, validate_params,
    exposure_coach, check_event_risk, breakout_plan,
    aggregate_signals, generate_hypotheses, detect_edge_decay,
    ftd_detect, ghost_gate, dispatch_ticket
)

OUTPUT = os.path.expanduser("~/Desktop/scalp-report.txt")
PROXY = "http://127.0.0.1:7897"


def api_get(url):
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(url, headers={"User-Agent": "Scalp-Monitor/1.0"})
    try:
        with opener.open(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=10) as r:
            return json.loads(r.read())


def main():
    try:
        TZ = timezone(timedelta(hours=8))
        now = datetime.now(TZ).strftime("%m/%d %H:%M")
        sep = "━" * 54

        # ---- 数据采集 ----
        t = api_get("https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT-SWAP")['data'][0]
        price = float(t['last'])
        low, high = float(t['low24h']), float(t['high24h'])
        vol = float(t.get('vol24h', 0))
        chg = (price - float(t['open24h'])) / float(t['open24h']) * 100

        fr = api_get("https://www.okx.com/api/v5/public/funding-rate?instId=ETH-USDT-SWAP")
        rate = float(fr['data'][0]['fundingRate']) * 100

        fg = api_get("https://api.alternative.me/fng/?limit=1")
        fear = int(fg['data'][0]['value'])

        # K线
        candles = api_get("https://www.okx.com/api/v5/market/candles?instId=ETH-USDT-SWAP&bar=15m&limit=6")
        klines = [{'o': float(c[1]), 'h': float(c[2]), 'l': float(c[3]), 'c': float(c[4]), 'vol': float(c[5])} for c in candles['data'][:6]]
        latest = klines[0]
        body = abs(latest['c'] - latest['o'])
        wl = min(latest['c'], latest['o']) - latest['l']
        wu = latest['h'] - max(latest['c'], latest['o'])
        trend = "偏空" if latest['c'] < (latest['h']+latest['l'])/2 else "偏多"

        # 形态
        patterns = []
        if wl > body * 1.5: patterns.append("下影长")
        if wu > body * 1.5: patterns.append("上影长")
        if body < 0.5: patterns.append("缩体变盘")
        kline_signal = {"trend_bias": trend, "patterns": patterns}

        # ---- 1小时级别支撑/阻力 ----
        candles_1h = api_get("https://www.okx.com/api/v5/market/candles?instId=ETH-USDT-SWAP&bar=1H&limit=12")
        klines_1h = [{'o': float(c[1]), 'h': float(c[2]), 'l': float(c[3]), 'c': float(c[4]), 'vol': float(c[5])} for c in candles_1h['data'][:12]]
        h1_prices = [k['h'] for k in klines_1h]
        l1_prices = [k['l'] for k in klines_1h]
        h1_high = max(h1_prices)
        h1_low = min(l1_prices)
        h1_close = klines_1h[0]['c']
        h1_mid = (h1_high + h1_low) / 2

        # Find key S/R: most tested levels
        def find_sr_levels(prices, precision=1):
            levels = {}
            for p in prices:
                key = round(p / precision) * precision
                levels[key] = levels.get(key, 0) + 1
            return sorted(levels.items(), key=lambda x: x[1], reverse=True)

        resistance_levels = find_sr_levels(h1_prices, 2)
        support_levels = find_sr_levels(l1_prices, 2)
        sr_resistance = [r[0] for r in resistance_levels[:3] if r[0] > price]
        sr_support = [s[0] for s in support_levels[:3] if s[0] < price]

        # 1h trend
        h1_trend = "上升" if klines_1h[0]['c'] > klines_1h[6]['c'] else "下降" if klines_1h[0]['c'] < klines_1h[6]['c'] else "横盘"
        h1_range_pct = (h1_high - h1_low) / h1_low * 100 if h1_low > 0 else 0

        # ---- 金十消息面 ----
        geo_items, macro_items, crypto_items = [], [], []
        import_bias = "neutral"
        try:
            from jin10_fetch import Jin10
            j10 = Jin10()
            geo_items = j10.get_geopolitical_impact()
            macro_items = j10.get_macro_impact()
            crypto_items = j10.get_crypto_impact()
            import_bias = detect_news_bias(geo_items, macro_items, crypto_items)
            j10.close()
        except Exception:
            pass

        # ---- 短线信号 ----
        bias = "做空" if price < 2080 else "做多"
        pos = calc_position(DEFAULT_CFG, price, bias)
        sig_score, sig_details = score_signal(price, fear, rate, bias, import_bias, kline_signal)
        verdict, verdict_note = signal_verdict(sig_score)

        # ---- Alpha Skills 6 技能 ----
        # 1. urithiru: 3-lane verification
        uri_ok, uri_conf, uri_reasons = urithiru_check(price, bias, sig_score, import_bias, trend)

        # 2. mental-model: cognitive stress test
        mm = mental_model_check(bias, pos.entry, pos.stop, pos.tp, DEFAULT_CFG.account,
                                " | ".join(g["content"][:60] for g in geo_items[:2]))

        # 3. ibd-distribution: sell pressure assessment
        ibd = eth_distribution_check(klines, price, vol)

        # 4. market-news-analyst: impact grading
        news_grade = grade_news_impact(geo_items, macro_items, crypto_items)

        # 5. backtest-expert: parameter validation
        bt = validate_params(DEFAULT_CFG.stop_pts, DEFAULT_CFG.tp_pts,
                             DEFAULT_CFG.account, DEFAULT_CFG.leverage, DEFAULT_CFG.margin_pct)

        # 6-12. Additional skills
        stats = get_stats()
        cal_items = []
        try: cal_items = j10.get_today_events()
        except: pass
        exp_c = exposure_coach(ibd['risk'], news_grade['level'], sig_score)
        evt = check_event_risk(cal_items)
        brk = breakout_plan(price, high, low, bias)
        agg = aggregate_signals(sig_score, uri_ok, ibd['risk'], news_grade['level'], mm['verdict'])
        hyps = generate_hypotheses([], {"price": price, "bias": bias})
        edge = detect_edge_decay(stats)

        # 13-14. FTD + Ghost Auto-Trader
        ftd = ftd_detect(klines, price, vol)
        gate = ghost_gate(price, bias, pos.entry, pos.stop, pos.tp,
                          sig_score, verdict, uri_ok, uri_conf,
                          mm['verdict'], agg, edge)
        ticket = dispatch_ticket(gate['ticket']) if gate['gate_passed'] else None

        # ---- 报告 ----
        report = f"""{sep}
  {now}  ETH 短线面板
{sep}

  价格 ${price:.2f}  │  日跌 {chg:+.2f}%
  24h H ${high:.2f}  L ${low:.2f}
  F&G {fear}  │  费率 {rate:.4f}%

  K线(15m): {trend}  形态: {'、'.join(patterns) if patterns else '无'}
  消息: {import_bias.upper()}

  1H 趋势: {h1_trend}  │  区间: ${h1_low:.0f} - ${h1_high:.0f} ({h1_range_pct:.1f}%)
  阻力: {', '.join(f'${r}' for r in sr_resistance[:3]) if sr_resistance else '无'}
  支撑: {', '.join(f'${s}' for s in sr_support[:3]) if sr_support else '无'}

{sep}
  短线信号
{sep}

  方向     {bias}
  入场     ${pos.entry}  止损 ${pos.stop}  止盈 ${pos.tp}
  R        = 1:{pos.rr}
  保证金   {pos.margin}U  ({pos.size}张)

  评分     {sig_score}/100  {verdict}
  趋势     {sig_details.get('趋势','')}  │  情绪  {sig_details.get('情绪','')}
  消息     {sig_details.get('消息','')}  │  执行  {sig_details.get('执行','')}
  →       {verdict_note}

{sep}
  Alpha Skills 六技能
{sep}
  Urithiru    {'PASS' if uri_ok else 'FAIL'} ({uri_conf}%)  {' | '.join(uri_reasons)}
  思维模型    {mm['verdict']}  (逆: {len(mm['inversion'])} / 一阶: {len(mm['first_principles'])} / 二阶: {len(mm['second_order'])})
  IBD 风险    {ibd['risk']} ({ibd['d_count']}派发/{ibd['lookback_candles']}烛)
  消息分级    {news_grade['level']} (均{news_grade['avg_impact']}/10)
  参数验证    {'OK' if bt['valid'] else ', '.join(bt['issues'])}  RR={bt['rr']}  最大亏{bt['max_loss_pct']}%

{sep}
  高级技能
{sep}
  敞口管理    {exp_c['exposure_pct']}% → {exp_c['recommendation']}
  事件预警    {evt['risk']} {', '.join(w['title'][:30] for w in evt['warnings']) if evt['warnings'] else '无临近事件'}
  突破追单    {brk['trigger']}  入场{brk['entry']}  R=1:{brk['rr']}  {'可用' if brk['valid'] else '不可用'}
  信号聚合    共识 {agg['conviction']:.0f}% ({agg['consensus']})  {'GO' if agg['go'] else 'WAIT'}
  假说探测    {hyps[0]['statement'][:40]}... (置信{hyps[0]['confidence']}%)
  策略健康    {edge.get('status','?')} → {edge.get('action','?')}
  FTD 检测    {ftd['state']} (修正{ftd['correction_pct']}%) → {ftd['action'][:40]}
  Ghost 门禁   {'PASS' if gate['gate_passed'] else 'FAIL'} ({gate['reason']})  {'→ 已出票' if ticket else '→ 不出票'}"""

        if ticket:
            report += f"""
{sep}
  交易指令（Ghost Auto-Trader）
{sep}
{ticket['message']}"""

        # 消息快讯
        all_items = []
        for src, items in [("地缘", geo_items), ("宏观", macro_items), ("加密", crypto_items)]:
            for item in items[:2]:
                all_items.append(f"[{src}] {item['time'][:5]} {item['content'][:60]}")
        if all_items:
            report += f"\n\n{sep}\n  消息雷达\n{sep}\n  " + "\n  ".join(all_items[:5])

        # 交易统计
        stats = get_stats()
        if stats and stats.get("total", 0) > 0:
            report += f"""
{sep}
  交易统计
{sep}
  总{stats['total']}单 | 胜{stats['wins']}败{stats['losses']} | 胜率{stats['win_rate']}%
  累计 {stats['total_pnl']:+.2f}U | 均盈{stats['avg_win']:.2f} | 均亏{stats['avg_loss']:.2f}"""

        report += "\n"

        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[{now}] OK. ETH {price} -> {bias} {verdict} ({sig_score}/100)")

    except Exception as e:
        err_msg = f"[出错] {datetime.now().strftime('%m/%d %H:%M')} - {e}\n"
        print(err_msg)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(err_msg)


if __name__ == "__main__":
    main()
