import pytest
from src.domain import tickets as rules
from src.domain.analysis import analyze, seed as seed_differences


def ticket(code, segment, procedure, kind, minutes, target=None, day='2026-11-10'):
    return {'code': code, 'segment': segment, 'procedure': procedure, 'kind': kind,
            'minutes': minutes, 'target_code': target, 'inspected_on': day}


def pair_rows(count=8):
    rows = []
    for i, difference in enumerate(seed_differences()[:count]):
        old = round(24 + (7 * i % 15) * 0.8, 2)
        rows.append(ticket(f'SJ-{i + 1:02d}-O-01', f'SJ-{i + 1:02d}', 'old', 'initial', old))
        rows.append(ticket(f'SJ-{i + 1:02d}-N-01', f'SJ-{i + 1:02d}', 'new', 'initial', round(old + difference, 2)))
    return rows


def run(rows, margin=2, alpha=0.05):
    resolution = rules.resolve(rows)
    return resolution, analyze(resolution['pairs'], {'margin_minutes': margin, 'alpha': alpha},
                               resolution['missing'], resolution['issues'])


def test_resolution_is_order_independent():
    rows = pair_rows()
    correction = ticket('SJ-01-O-C1', 'SJ-01', 'old', 'correction', 25.5, 'SJ-01-O-01')
    forward = rules.resolve(rows + [correction])
    backward = rules.resolve([correction] + rows)
    assert forward['ticket_status'] == backward['ticket_status']
    assert forward['live']['SJ-01']['old'][0]['minutes'] == 25.5
    assert forward['ticket_status']['SJ-01-O-01'] == 'replaced'


def test_withdrawal_restores_replaced_ticket():
    rows = pair_rows()
    rows += [ticket('SJ-01-O-C1', 'SJ-01', 'old', 'correction', 25.5, 'SJ-01-O-01'),
             ticket('SJ-01-O-W1', 'SJ-01', 'old', 'withdrawal', None, 'SJ-01-O-C1')]
    resolution = rules.resolve(rows)
    assert resolution['ticket_status']['SJ-01-O-C1'] == 'withdrawn'
    assert resolution['ticket_status']['SJ-01-O-01'] == 'valid'
    assert [row['minutes'] for row in resolution['live']['SJ-01']['old']] == [24.0]


def test_missing_side_is_listed_not_compared():
    rows = [row for row in pair_rows() if row['code'] != 'SJ-02-O-01']
    resolution, result = run(rows)
    assert [row['segment'] for row in resolution['missing']] == ['SJ-02']
    assert resolution['missing'][0]['sides'][0]['reason'] == 'no_ticket'
    assert result['verdict'] in {'equivalent', 'longer', 'shorter', 'insufficient'}
    assert result['metrics'][0]['value'] == 7
    assert '缺单' in result['summary']


def test_withdrawn_side_blocks_only_that_segment():
    rows = pair_rows() + [ticket('SJ-03-O-W1', 'SJ-03', 'old', 'withdrawal', None, 'SJ-03-O-01')]
    resolution, _ = run(rows)
    assert resolution['ticket_status']['SJ-03-O-01'] == 'withdrawn'
    assert resolution['missing'][0]['sides'][0]['reason'] == 'withdrawn'


def test_duplicate_value_retest_keeps_single_configuration():
    rows = pair_rows() + [ticket('SJ-01-N-02', 'SJ-01', 'new', 'retest', 20.5)]
    resolution, result = run(rows)
    assert resolution['ambiguous'] == []
    assert result['configurations']['total'] == 1


def test_disagreeing_configurations_withhold_verdict():
    rows = pair_rows() + [ticket('SJ-05-N-02', 'SJ-05', 'new', 'retest', 80.0)]
    resolution, result = run(rows)
    assert result['configurations']['total'] == 2
    assert result['consistent'] is False
    assert result['verdict'] == 'inconsistent'
    assert result['configurations']['blocking']
    assert '裁决不一致' in result['headline']


def test_agreeing_configurations_give_verdict():
    rows = pair_rows() + [ticket('SJ-05-N-02', 'SJ-05', 'new', 'retest', 32.4)]
    resolution, result = run(rows)
    assert result['configurations']['total'] == 2
    assert result['consistent'] is True
    assert result['verdict'] == 'equivalent'


def test_conflicting_events_mark_segment():
    rows = pair_rows() + [ticket('SJ-04-O-C1', 'SJ-04', 'old', 'correction', 25.0, 'SJ-04-O-01'),
                          ticket('SJ-04-O-W1', 'SJ-04', 'old', 'withdrawal', None, 'SJ-04-O-01')]
    resolution = rules.resolve(rows)
    assert resolution['missing'][0]['sides'][0]['reason'] == 'conflict'
    assert resolution['ticket_status']['SJ-04-O-01'] == 'conflict'


def test_dangling_reference_blocks_side():
    rows = pair_rows() + [ticket('SJ-06-O-C9', 'SJ-06', 'old', 'correction', 25.0, 'SJ-99-O-01')]
    resolution = rules.resolve(rows)
    assert resolution['issues'][0]['reason'] == 'unresolved_target'
    assert resolution['missing'][0]['sides'][0]['reason'] == 'unresolved'


def test_side_mismatch_reference_rejected():
    rows = pair_rows() + [ticket('SJ-07-O-C1', 'SJ-07', 'old', 'correction', 25.0, 'SJ-07-N-01')]
    resolution = rules.resolve(rows)
    assert resolution['issues'][0]['reason'] == 'target_side_mismatch'


def test_duplicate_code_rejected():
    rows = pair_rows()
    with pytest.raises(ValueError):
        rules.resolve(rows + [rows[0]])


def test_too_few_segments_rejected():
    with pytest.raises(ValueError):
        run(pair_rows(2))


def test_no_variation_rejected():
    rows = [ticket('A-O', 'A', 'old', 'initial', 10), ticket('A-N', 'A', 'new', 'initial', 11),
            ticket('B-O', 'B', 'old', 'initial', 20), ticket('B-N', 'B', 'new', 'initial', 21),
            ticket('C-O', 'C', 'old', 'initial', 30), ticket('C-N', 'C', 'new', 'initial', 31)]
    with pytest.raises(ValueError):
        run(rows)


def test_business_interval_reproduced():
    _, result = run(pair_rows(32))
    metrics = {metric['label']: metric['value'] for metric in result['metrics']}
    assert metrics['样本均差（新减旧）'] == 0.2812
    assert metrics['90% 置信区间'] == '[-0.2410, 0.8035]'
    assert result['verdict'] == 'equivalent'
