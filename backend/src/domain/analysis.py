"""Paired TOST for heating inspection times across one batch of segments.

Each segment keeps every effective timing ticket per procedure.  Before a
verdict is issued the analysis walks every complete choice of one old and one
new ticket per segment ("配法").  A conclusion is only issued when every
configuration yields the same verdict; otherwise the conflicting configurations
are reported so the workbench can show what is blocking the decision.
"""

from decimal import Decimal, InvalidOperation
from math import sqrt
from statistics import mean, stdev

from scipy.stats import t

from src.constants.enums import Procedure
from src.domain import tickets as ticket_rules


MAX_CONFIGURATIONS = 512
VERDICT_LABELS = {
    'equivalent': '达到等效',
    'longer': '新规程超容许偏长',
    'shorter': '新规程超容许偏短',
    'insufficient': '等效证据不足',
    'inconsistent': '配法裁决不一致',
    'error': '无法估计',
}


def _number(value, label, low, high):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}必须是有效数字。') from None
    if not number.is_finite() or not Decimal(str(low)) <= number <= Decimal(str(high)):
        raise ValueError(f'{label}必须在 {low} 到 {high} 之间。')
    return number


def _direction(average):
    if average > 0:
        return '新规程较慢'
    if average < 0:
        return '新规程较快'
    return '平均工时相同'


def evaluate(differences: list[float], margin: float, alpha: float) -> dict:
    """Run one paired TOST and classify the result."""
    n = len(differences)
    if n < 3:
        raise ValueError('配对等效检验至少需要 3 个完整区段，每段均须有新旧两项有效计时。')
    average = float(mean(differences))
    sd = float(stdev(differences))
    if sd == 0:
        raise ValueError('所有区段的配对差相同，无法估计差值波动。请核对计时精度或补采区段。')
    se = sd / sqrt(n)
    df = n - 1
    cutoff = float(t.isf(alpha, df))
    lower, upper = average - cutoff * se, average + cutoff * se
    lower_stat = (average + margin) / se
    upper_stat = (margin - average) / se
    lower_p = float(t.sf(lower_stat, df))
    upper_p = float(t.sf(upper_stat, df))
    if min(lower_stat, upper_stat) > cutoff:
        verdict = 'equivalent'
    elif lower > margin:
        verdict = 'longer'
    elif upper < -margin:
        verdict = 'shorter'
    else:
        verdict = 'insufficient'
    return {
        'verdict': verdict,
        'n': n,
        'average': average,
        'direction': _direction(average),
        'sd': sd,
        'se': se,
        'cutoff': cutoff,
        'lower': lower,
        'upper': upper,
        'lower_p': lower_p,
        'upper_p': upper_p,
    }


def _configuration_view(configuration, evaluation):
    return {
        'tickets': ticket_rules.configuration_summary(configuration),
        'verdict': evaluation['verdict'],
        'verdict_label': VERDICT_LABELS[evaluation['verdict']],
        'average': round(evaluation['average'], 4),
        'interval': [round(evaluation['lower'], 4), round(evaluation['upper'], 4)],
    }


def _configuration_differences(configuration):
    return [side['new']['minutes'] - side['old']['minutes'] for side in configuration.values()]


def analyze(pairs: dict, parameters: dict, missing=None, issues=None) -> dict:
    """Evaluate one batch snapshot.

    ``pairs`` maps segment -> {'old': [ticket, ...], 'new': [ticket, ...]}.  A
    segment with an empty side never appears here; it is reported in ``missing``.
    """
    margin_decimal = _number(parameters.get('margin_minutes', 2), '等效容许差（分钟）', 0.01, 120)
    margin = float(margin_decimal)
    alpha = float(_number(parameters.get('alpha', 0.05), '单侧显著性水平', 0.001, 0.2))
    missing = missing or []
    issues = issues or []
    if not pairs:
        raise ValueError('没有新旧两侧都齐的区段，无法开始配对检验。请补采缺单或核对引用。')
    segments = sorted(pairs)
    total = ticket_rules.configuration_count(pairs)
    if total > MAX_CONFIGURATIONS:
        raise ValueError(f'补测与有效计时共形成 {total} 种配法，超过一次复核的 {MAX_CONFIGURATIONS} 种上限。'
                         '请先撤回多余计时或核对补测工单。')

    results = []
    for configuration in ticket_rules.configurations(pairs):
        evaluation = evaluate(_configuration_differences(configuration), margin, alpha)
        results.append((configuration, evaluation))

    distributions = {}
    for _, evaluation in results:
        distributions[evaluation['verdict']] = distributions.get(evaluation['verdict'], 0) + 1
    consistent = len(distributions) == 1
    canonical = ticket_rules.canonical_configuration(pairs)
    canonical_evaluation = next(evaluation for configuration, evaluation in results
                                if configuration == canonical)
    counts = sorted(distributions.items(), key=lambda item: (-item[1], item[0]))
    blocking = []
    if not consistent:
        majority = counts[0][0]
        for configuration, evaluation in results:
            if evaluation['verdict'] == majority:
                continue
            blocking.append(_configuration_view(configuration, evaluation))
            if len(blocking) >= 20:
                break

    detail = []
    for segment, side in canonical.items():
        old, new = side['old'], side['new']
        difference = new['minutes'] - old['minutes']
        detail.append({
            'segment': segment,
            'old_code': old['code'],
            'new_code': new['code'],
            'old_minutes': float(old['minutes']),
            'new_minutes': float(new['minutes']),
            'difference': round(float(difference), 4),
            'review': '复核' if abs(difference) > margin_decimal else '界内',
        })
    detail.sort(key=lambda row: (-abs(row['difference']), row['segment']))

    active = canonical_evaluation
    interval = f'[{active["lower"]:.4f}, {active["upper"]:.4f}]'
    confidence = f'{100 * (1 - 2 * alpha):.4g}%'
    distribution_text = '，'.join(f'{VERDICT_LABELS[verdict]} {count} 种' for verdict, count in counts)
    if consistent:
        verdict = counts[0][0]
        if verdict == 'equivalent':
            headline = '所有配法下配对工时均达到等效标准'
            recommendation = '各配法的两道单侧门槛一致通过，可提交运行主管限量并行复核。'
        elif verdict == 'longer':
            headline = '所有配法下新规程工时均偏长'
            recommendation = '各配法区间均整体高于正容许界，建议暂沿用旧规程并检查新增步骤。'
        elif verdict == 'shorter':
            headline = '所有配法下新规程工时均偏短'
            recommendation = '各配法区间均整体低于负容许界，建议复核计时和巡检覆盖，再由主管评估。'
        else:
            headline = '所有配法下工时等效证据不足'
            recommendation = '各配法区间均触及或跨越容许界，建议继续平行采样并优先复核偏差较大的区段。'
        summary = recommendation
    else:
        verdict = 'inconsistent'
        headline = '新旧计时存在多种可行配法，裁决不一致，暂不给出等效结论'
        recommendation = (f'当前有效计时形成 {total} 种配法，裁决分布为 {distribution_text}。'
                          '请核对补测、更正与撤回工单，使每个区段只剩一种明确配法后再复核。')
        summary = recommendation
    if missing:
        summary += f'另有 {len(missing)} 个区段缺一侧有效计时，已列入缺单，不参与本次检验。'
    if issues:
        summary += f'有 {len(issues)} 张更正或撤回工单尚未生效，请在工作台核对引用。'
    summary += '工时结论适用于可比工况下的独立区段，巡检覆盖率和漏检须另行复核。'

    metrics = [
        {'label': '独立配对区段', 'value': active['n'], 'unit': '段'},
        {'label': '样本均差（新减旧）', 'value': round(active['average'], 4), 'unit': '分钟'},
        {'label': '样本均差方向', 'value': active['direction']},
        {'label': f'{confidence} 置信区间', 'value': interval, 'unit': '分钟'},
        {'label': '预设等效容许差', 'value': margin, 'unit': '±分钟'},
        {'label': '超过负容许界的单侧 p 值', 'value': active['lower_p']},
        {'label': '低于正容许界的单侧 p 值', 'value': active['upper_p']},
        {'label': '可行配法组合', 'value': total, 'unit': '种'},
        {'label': '配法裁决一致性', 'value': '全部一致' if consistent else distribution_text},
    ]
    if missing:
        metrics.append({'label': '缺单区段', 'value': len(missing), 'unit': '段'})

    result = {
        'verdict': verdict,
        'verdict_label': VERDICT_LABELS[verdict],
        'consistent': consistent,
        'headline': headline,
        'summary': summary,
        'metrics': metrics,
        'columns': [
            {'key': 'segment', 'label': '巡检区段'},
            {'key': 'old_code', 'label': '旧规程工单'},
            {'key': 'new_code', 'label': '新规程工单'},
            {'key': 'old_minutes', 'label': '旧规程（分钟）'},
            {'key': 'new_minutes', 'label': '新规程（分钟）'},
            {'key': 'difference', 'label': '新减旧（分钟）'},
            {'key': 'review', 'label': '单段工时核对'},
        ],
        'rows': detail,
        'chart': {
            'label': f'均差及 {confidence} 区间端点与等效界值',
            'unit': '分钟',
            'points': [
                {'label': '负容许界', 'value': -margin},
                {'label': '区间下限', 'value': round(active['lower'], 4)},
                {'label': '样本均差', 'value': round(active['average'], 4)},
                {'label': '区间上限', 'value': round(active['upper'], 4)},
                {'label': '正容许界', 'value': margin},
            ],
        },
        'configurations': {
            'total': total,
            'consistent': consistent,
            'verdicts': [{'verdict': verdict, 'label': VERDICT_LABELS[verdict], 'count': count}
                         for verdict, count in counts],
            'blocking': blocking,
        },
        'canonical': ticket_rules.configuration_summary(canonical),
        'pairs': {segment: {proc: [{'code': item['code'], 'minutes': item['minutes']}
                                   for item in side[proc]]
                            for proc in (str(Procedure.OLD), str(Procedure.NEW))}
                  for segment, side in pairs.items()},
        'missing': missing,
        'issues': issues,
    }
    return result


def seed() -> list[dict]:
    """Demonstration differences; the same 32 pairs the business script cites."""
    return [
        -3.5, -0.6, 0.8, 2.2, -2.1, 1.2, 0.4, -0.9,
        1.9, 3.1, -2.8, 0.6, 1.7, -0.7, 0.9, -0.1,
        2.8, -1.5, 0.5, -1.1, 2.1, 0.7, -2.4, 1.6,
        3.3, -0.2, -1.6, 1.1, 0.0, 2.5, -0.5, -0.4,
    ]
