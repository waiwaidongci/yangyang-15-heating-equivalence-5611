"""Paired TOST for heating inspection times."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from math import sqrt
from statistics import mean, stdev

from scipy.stats import t


def _number(value, label, low, high):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label}必须是有效数字。") from None
    if not number.is_finite() or not Decimal(str(low)) <= number <= Decimal(str(high)):
        raise ValueError(f"{label}必须在 {low} 到 {high} 之间。")
    return number


def _parse(row):
    segment = row.get("segment")
    if not isinstance(segment, str) or not segment.strip():
        raise ValueError("请填写巡检区段编号。")
    segment = segment.strip()
    day = row.get("inspection_date")
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"区段 {segment} 的巡检日期必须采用 YYYY-MM-DD 格式。") from None
    old = _number(row.get("old_minutes"), f"区段 {segment} 的旧规程工时（分钟）", 0.01, 480)
    new = _number(row.get("new_minutes"), f"区段 {segment} 的新规程工时（分钟）", 0.01, 480)
    return segment, day, old, new


def validate(row: dict):
    _parse(row)


def seed() -> list[dict]:
    differences = [
        -3.5, -0.6, 0.8, 2.2, -2.1, 1.2, 0.4, -0.9,
        1.9, 3.1, -2.8, 0.6, 1.7, -0.7, 0.9, -0.1,
        2.8, -1.5, 0.5, -1.1, 2.1, 0.7, -2.4, 1.6,
        3.3, -0.2, -1.6, 1.1, 0.0, 2.5, -0.5, -0.4,
    ]
    start = date(2026, 11, 9)
    rows = []
    for i, difference in enumerate(differences):
        old = 24 + (7 * i % 15) * 0.8
        rows.append({
            "segment": f"SJ-{i + 1:02d}",
            "inspection_date": (start + timedelta(days=i // 4)).isoformat(),
            "old_minutes": round(old, 2),
            "new_minutes": round(old + difference, 2),
        })
    return rows


def analyze(rows: list[dict], parameters: dict) -> dict:
    margin_decimal = _number(parameters.get("margin_minutes", 2), "等效容许差（分钟）", 0.01, 120)
    margin = float(margin_decimal)
    alpha = float(_number(parameters.get("alpha", 0.05), "单侧显著性水平", 0.001, 0.2))
    records = {}
    for row in rows:
        segment, day, old, new = _parse(row)
        if segment in records:
            raise ValueError(f"区段 {segment} 重复。每个区段只保留一条新旧配对工时。")
        records[segment] = day, old, new
    n = len(records)
    if n < 3:
        raise ValueError("配对等效检验至少需要 3 个独立区段，每段均须有新旧两项工时。")

    differences = [new - old for _, old, new in records.values()]
    average = float(mean(differences))
    sd = float(stdev(differences))
    if sd == 0:
        raise ValueError("所有区段的配对差相同，无法估计差值波动。请核对计时精度或补采区段。")
    se = sd / sqrt(n)
    df = n - 1
    cutoff = float(t.isf(alpha, df))
    lower, upper = average - cutoff * se, average + cutoff * se
    lower_stat = (average + margin) / se
    upper_stat = (margin - average) / se
    lower_p = float(t.sf(lower_stat, df))
    upper_p = float(t.sf(upper_stat, df))
    equivalent = min(lower_stat, upper_stat) > cutoff

    if equivalent:
        headline = "配对工时达到等效标准"
        recommendation = "两道单侧门槛均通过，建议将新规程提交运行主管限量并行复核。"
    elif lower > margin:
        headline = "新规程工时偏长，超过容许差"
        recommendation = "区间整体在正容许界外，建议暂沿用旧规程并检查新增步骤。"
    elif upper < -margin:
        headline = "新规程工时偏短，超过容许差"
        recommendation = "区间整体在负容许界外，建议复核计时和巡检覆盖，再由主管评估新规程。"
    else:
        headline = "工时等效证据不足"
        recommendation = "区间触及或跨越容许界，建议继续平行采样并优先复核偏差较大的区段。"
    if average > 0:
        direction = "新规程较慢"
    elif average < 0:
        direction = "新规程较快"
    else:
        direction = "平均工时相同"
    confidence = f"{100 * (1 - 2 * alpha):.4g}%"

    detail = []
    for segment, (day, old, new) in sorted(records.items(), key=lambda item: (-abs(item[1][2] - item[1][1]), item[0])):
        difference = new - old
        detail.append({
            "segment": segment,
            "inspection_date": day,
            "old_minutes": float(old),
            "new_minutes": float(new),
            "difference": round(float(difference), 4),
            "review": "复核" if abs(difference) > margin_decimal else "界内",
        })
    return {
        "headline": headline,
        "summary": recommendation + "工时结论适用于可比工况下的独立区段，巡检覆盖率和漏检须另行复核。",
        "metrics": [
            {"label": "独立配对区段", "value": n, "unit": "段"},
            {"label": "样本均差（新减旧）", "value": round(average, 4), "unit": "分钟"},
            {"label": "样本均差方向", "value": direction},
            {"label": f"{confidence} 置信区间", "value": f"[{lower:.4f}, {upper:.4f}]", "unit": "分钟"},
            {"label": "预设等效容许差", "value": margin, "unit": "±分钟"},
            {"label": "超过负容许界的单侧 p 值", "value": lower_p},
            {"label": "低于正容许界的单侧 p 值", "value": upper_p},
        ],
        "columns": [
            {"key": "segment", "label": "巡检区段"},
            {"key": "inspection_date", "label": "巡检日期"},
            {"key": "old_minutes", "label": "旧规程（分钟）"},
            {"key": "new_minutes", "label": "新规程（分钟）"},
            {"key": "difference", "label": "新减旧（分钟）"},
            {"key": "review", "label": "单段工时核对"},
        ],
        "rows": detail,
        "chart": {
            "label": f"均差及 {confidence} 区间端点与等效界值",
            "unit": "分钟",
            "points": [
                {"label": "负容许界", "value": -margin},
                {"label": "区间下限", "value": round(lower, 4)},
                {"label": "样本均差", "value": round(average, 4)},
                {"label": "区间上限", "value": round(upper, 4)},
                {"label": "正容许界", "value": margin},
            ],
        },
    }
