        prev = previous_stocks.get(row["code"], {})
        streak = int(prev.get("streak", 0) or 0) + 1
        new_state["stocks"][row["code"]] = {
            "name": row["name"],
            "streak": streak,
            "last_group": row["group"],
            "last_score": row["score"],
            "last_theme": row["theme"],
        }
    previous_funds = previous_state.get("funds", {})
    for fund in funds:
        key = f"{fund['type']}:{fund['code']}"
        prev = previous_funds.get(key, {})
        streak = int(prev.get("streak", 0) or 0) + 1
        new_state["funds"][key] = {
            "name": fund["name"],
            "streak": streak,
            "last_group": fund["group"],
            "last_score": fund["score"],
            "last_theme": fund["theme"],
        }
    return new_state


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def pct(value: Any, digits: int = 1) -> str:
    return f"{to_float(value):.{digits}f}%"


def wan(value: Any) -> str:
    return f"{to_float(value) / 10000:.1f}万"


def risk_class(risk_level: str) -> str:
    return {"低风险": "ok", "中风险": "warn", "高风险": "danger"}.get(risk_level, "warn")


def render_group_cards(groups: dict[str, list[dict[str, Any]]], group_order: list[str], kind: str = "stock") -> str:
    cards = []
    for group in group_order:
        rows = groups.get(group, [])
        if not rows:
            continue
        items = []
        for row in rows[:8]:
            if kind == "stock":
                subtitle = f"{row['code']} | {pct(row['change_rate'])} | {row['theme']} | {row['risk_level']}"
            else:
                subtitle = f"{row['code']} | {row['type']} | {row['theme']} | {row['risk_level']}"
            items.append(
                f"""
                <div class="mini-item">
                  <div><b>{esc(row['name'])}</b> <span class="score">{esc(row['score'])}</span></div>
                  <div class="muted">{esc(subtitle)}</div>
                  <div class="muted">{esc(row.get('action_tip', ''))}</div>
                </div>
                """
            )
        cards.append(
            f"""
            <div class="pool">
              <div class="pool-title">{esc(group)} <span>{len(rows)}只</span></div>
              {''.join(items)}
            </div>
            """
        )
    return "".join(cards) or '<p class="muted">暂无符合条件的观察对象。</p>'


def render_stock_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for idx, row in enumerate(rows[:20], 1):
        risks = "；".join(row["risk_flags"]) if row["risk_flags"] else "无明显风险"
        body.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><b>{esc(row['name'])}</b><br><span class="muted">{esc(row['code'])}</span></td>
              <td><b>{pct(row['recommend_ratio'])}</b><br><span class="muted">涨幅 {pct(row['change_rate'])}</span></td>
              <td>{esc(row['theme'])}<br><span class="pill">{esc(row['theme_linkage'])}，同向{row['theme_peer_count']}只</span></td>
              <td>{esc(row['trend_status'])}<br><span class="muted">量比 {esc(row.get('volume_ratio', 0))}</span></td>
              <td>{esc(row['pressure_status'])}</td>
              <td><span class="tag {risk_class(row['risk_level'])}">{esc(row['risk_level'])}</span><br><span class="muted">{esc(risks)}</span></td>
              <td>{esc(row['action_tip'])}<br><span class="muted">{esc(row['memory_note'])}</span></td>
            </tr>
            """
        )
    return "".join(body)


def render_fund_table(funds: list[dict[str, Any]]) -> str:
    body = []
    for idx, fund in enumerate(funds[:20], 1):
        risks = "；".join(fund["risk_flags"]) if fund["risk_flags"] else "无明显风险"
        body.append(
            f"""
            <tr>
              <td>{idx}</td>
              <td><b>{esc(fund['name'])}</b><br><span class="muted">{esc(fund['code'])} | {esc(fund['type'])}</span></td>
              <td><b>{esc(fund['score'])}</b><br><span class="muted">{esc(fund['group'])}</span></td>
              <td>{esc(fund['theme'])}</td>
              <td>{esc(fund['trend_status'])}<br><span class="muted">20日 {pct(fund.get('return_20', 0))}</span></td>
              <td>{esc(fund['pressure_status'])}<br><span class="muted">回撤 {pct(fund.get('max_drawdown_60', 0))}</span></td>
              <td><span class="tag {risk_class(fund['risk_level'])}">{esc(fund['risk_level'])}</span><br><span class="muted">{esc(risks)}</span></td>
              <td>{esc(fund['action_tip'])}<br><span class="muted">{esc(fund['memory_note'])}</span></td>
            </tr>
            """
        )
    return "".join(body)


def render_html_report(report: dict[str, Any]) -> str:
    stocks = report["stocks"]
    funds = report["funds"]
    stock_groups = group_rows(stocks)
    fund_groups = group_rows(funds)
    themes = report["themes"]
    mode_label = "14点综合观察" if report["mode"] == "full" else "12点股票观察"
    best_line = (
        f"今日符合5%-10%涨幅硬条件的股票共 {len(stocks)} 只，最高观察对象为 {stocks[0]['name']}（{stocks[0]['recommend_ratio']}%）。"
        if stocks
        else "今日暂未筛出符合5%-10%涨幅硬条件的龙虎榜股票。"
    )
    theme_html = "".join(
        f"""
        <div class="theme-row">
          <b>{esc(item['theme'])}</b>
          <span>{esc(item['linkage'])} | {item['count']}只 | 高分{item['high_count']}只 | 均分{item['avg_score']}</span>
        </div>
        """
        for item in themes[:8]
    )
    if not theme_html:
        theme_html = '<p class="muted">暂无强方向。</p>'

    fund_section = ""
    if report["mode"] == "full":
        fund_section = f"""
        <section class="card">
          <h2>基金/ETF观察池</h2>
          <div class="pools">
            {render_group_cards(fund_groups, ["趋势观察池", "回调低吸池", "高位谨慎池", "暂不参与池"], kind="fund")}
          </div>
        </section>
        <section class="card">
          <h2>基金/ETF详情</h2>
          <table>
            <thead><tr><th>#</th><th>基金</th><th>评分/分组</th><th>匹配方向</th><th>趋势</th><th>压力/回撤</th><th>风险</th><th>观察提示</th></tr></thead>
            <tbody>{render_fund_table(funds)}</tbody>
          </table>
        </section>
        """

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(mode_label)} - {esc(report['trade_date'])}</title>
  <style>
    body {{ margin:0; background:#f6f8fb; color:#172033; font-family:Arial,'Microsoft YaHei',sans-serif; line-height:1.55; }}
    .wrap {{ max-width:1180px; margin:0 auto; padding:18px; }}
    .hero {{ background:#10233f; color:white; border-radius:8px; padding:20px; }}
    h1 {{ margin:0 0 8px; font-size:24px; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    .muted {{ color:#667085; font-size:12px; }}
    .hero .muted {{ color:#d8e4f5; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:14px 0; }}
    .metric,.card,.pool {{ background:white; border:1px solid #e4e7ec; border-radius:8px; padding:14px; }}
    .metric b {{ display:block; font-size:24px; margin-top:4px; }}
    .card {{ margin-top:14px; }}
    .pools {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    .pool-title {{ font-weight:700; margin-bottom:8px; display:flex; justify-content:space-between; }}
    .mini-item {{ border-top:1px solid #eef1f5; padding:8px 0; }}
    .score {{ color:#2563eb; font-weight:700; }}
    .theme-row {{ display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid #eef1f5; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 7px; border-bottom:1px solid #e4e7ec; vertical-align:top; text-align:left; }}
    th {{ background:#f9fafb; }}
    .pill {{ display:inline-block; margin-top:3px; padding:2px 7px; border-radius:999px; background:#eef2ff; color:#3730a3; font-size:12px; }}
    .tag {{ display:inline-block; padding:2px 7px; border-radius:999px; font-size:12px; font-weight:700; }}
    .ok {{ background:#ecfdf3; color:#027a48; }}
    .warn {{ background:#fff7e6; color:#b54708; }}
    .danger {{ background:#fef3f2; color:#b42318; }}
    .notice {{ font-size:12px; color:#667085; margin-top:12px; }}
    @media(max-width:900px) {{ .grid,.pools {{ grid-template-columns:1fr; }} .wrap {{ padding:10px; }} table {{ font-size:12px; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>{esc(mode_label)} - {esc(report['trade_date'])}</h1>
      <div>{esc(best_line)}</div>
      <div class="muted">硬规则：只筛选当日涨幅 5%-10% 的龙虎榜股票；同花顺70% + 东方财富30%；本报告仅用于观察和研究。</div>
    </section>
    <section class="grid">
      <div class="metric">股票候选<b>{len(stocks)}</b></div>
      <div class="metric">强方向<b>{sum(1 for item in themes if item['linkage'] in ('联动强','联动中'))}</b></div>
      <div class="metric">低吸观察<b>{len(stock_groups.get('低吸观察池', []))}</b></div>
      <div class="metric">基金候选<b>{len(funds) if report['mode'] == 'full' else '-'}</b></div>
    </section>
    <section class="card">
      <h2>强方向 / 板块联动</h2>
      {theme_html}
    </section>
    <section class="card">
      <h2>股票观察池</h2>
      <div class="pools">
        {render_group_cards(stock_groups, ["低吸观察池", "突破确认池", "只看不追池", "风险回避池"], kind="stock")}
      </div>
    </section>
    {fund_section}
    <section class="card">
      <h2>股票详情</h2>
      <table>
        <thead><tr><th>#</th><th>股票</th><th>推荐比例</th><th>方向/联动</th><th>趋势</th><th>压力位</th><th>风险</th><th>操作提示</th></tr></thead>
        <tbody>{render_stock_table(stocks)}</tbody>
      </table>
    </section>
    <div class="notice">
      数据源记录：同花顺 {report['source_counts'].get('tonghuashun', 0)} 条，东方财富 {report['source_counts'].get('eastmoney', 0)} 条。
      {esc('；'.join(report.get('errors', [])))}
      本系统不构成任何股票、基金、证券或金融产品的买卖建议。
    </div>
  </div>
</body>
</html>"""


def write_stock_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "rank",
        "group",
        "code",
        "name",
        "score",
        "recommend_ratio",
        "change_rate",
        "theme",
        "theme_linkage",
        "risk_level",
        "trend_status",
        "pressure_status",
        "action_tip",
        "memory_note",
        "platforms",
