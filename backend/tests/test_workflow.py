from conftest import install_fake_redis

import pytest
from fastapi.testclient import TestClient

from src.domain.analysis import seed as seed_differences
from src.main import app
from src.models.base import Session
from src.services.runs import run_pending

PASSWORDS = {'analyst@demo.local': 'Analyst-2026!', 'supervisor@demo.local': 'Supervisor-2026!',
             'viewer@demo.local': 'Viewer-2026!'}


@pytest.fixture(scope='module')
def client():
    install_fake_redis()
    with TestClient(app) as test_client:
        yield test_client


def auth(client, email):
    response = client.post('/api/auth/login', json={'email': email, 'password': PASSWORDS[email]})
    assert response.status_code == 200, response.text
    return {'Authorization': f'Bearer {response.json()["token"]}'}


def compute():
    with Session.begin() as db:
        return run_pending(db)


def ticket_rows(count=32):
    rows = []
    for i, difference in enumerate(seed_differences()[:count]):
        old = round(24 + (7 * i % 15) * 0.8, 2)
        segment = f'SJ-{i + 1:02d}'
        rows.append({'code': f'{segment}-O-01', 'segment': segment, 'procedure': 'old', 'kind': 'initial',
                     'minutes': old, 'inspected_on': '2026-11-10'})
        rows.append({'code': f'{segment}-N-01', 'segment': segment, 'procedure': 'new', 'kind': 'initial',
                     'minutes': round(old + difference, 2), 'inspected_on': '2026-11-10'})
    return rows


def new_batch(client, headers, name):
    response = client.post('/api/batches', json={'name': name, 'note': '测试'}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()['id']


def seed_batch(client, headers, name, count=32):
    batch = new_batch(client, headers, name)
    rows = ticket_rows(count)
    response = client.post(f'/api/batches/{batch}/tickets',
                           json={'tickets': [row for row in rows if '-O-' in row['code']]}, headers=headers)
    assert response.status_code == 201, response.text
    assert all(side['reason'] == 'no_ticket'
               for item in response.json()['missing'] for side in item['sides'])
    response = client.post(f'/api/batches/{batch}/tickets',
                           json={'tickets': [row for row in rows if '-N-' in row['code']]}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()['missing'] == []
    return batch


def create_run(client, headers, batch, title='复核'):
    response = client.post(f'/api/runs?batch_id={batch}',
                           json={'title': title, 'parameters': {'margin_minutes': 2, 'alpha': 0.05}}, headers=headers)
    assert response.status_code == 201, response.text
    compute()
    return response.json()['id']


def test_missing_side_excluded_and_flagged(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = new_batch(client, analyst, '缺单批次')
    rows = ticket_rows(10)
    client.post(f'/api/batches/{batch}/tickets',
                json={'tickets': [row for row in rows if row['segment'] != 'SJ-02' or '-N-' in row['code']]},
                headers=analyst)
    registry = client.get(f'/api/batches/{batch}/registry', headers=analyst).json()
    assert [row['segment'] for row in registry['missing']] == ['SJ-02']
    assert registry['missing'][0]['sides'][0]['reason'] == 'no_ticket'
    run_id = create_run(client, analyst, batch)
    body = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert body['status'] == 'succeeded'
    missing_metric = [metric for metric in body['result']['metrics'] if metric['label'] == '缺单区段']
    assert missing_metric and missing_metric[0]['value'] == 1
    assert body['result']['metrics'][0]['value'] == 9


def test_business_numbers_reproduced(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = seed_batch(client, analyst, '基准批次')
    run_id = create_run(client, analyst, batch)
    body = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    metrics = {metric['label']: metric['value'] for metric in body['result']['metrics']}
    assert metrics['独立配对区段'] == 32
    assert metrics['样本均差（新减旧）'] == 0.2812
    assert metrics['90% 置信区间'] == '[-0.2410, 0.8035]'
    assert body['result']['verdict'] == 'equivalent'


def test_retest_supersedes_unreviewed_and_signed_is_reproducible(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = seed_batch(client, analyst, '并发更正批次')
    run_id = create_run(client, analyst, batch)
    detail = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert detail['status'] == 'succeeded' and detail['stale'] is False
    signed_metrics = detail['result']['metrics']

    response = client.post(f'/api/batches/{batch}/tickets', json={'tickets': [
        {'code': 'SJ-01-N-02', 'segment': 'SJ-01', 'procedure': 'new', 'kind': 'retest',
         'minutes': 20.9, 'inspected_on': '2026-11-12'}]}, headers=analyst)
    assert response.status_code == 201, response.text

    # old version is stale and superseded by a queued recompute
    old = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert old['stale'] is True
    assert old['status'] == 'superseded'
    assert old['superseded_by'] is not None
    # old numbers are still reproducible from the frozen tickets
    repro = client.post(f'/api/runs/{run_id}/reproduce', headers=supervisor)
    assert repro.status_code == 200, repro.text
    assert repro.json()['matches'] is True
    assert repro.json()['metrics'] == signed_metrics
    # the stale version cannot be signed any more
    blocked = client.post(f'/api/runs/{run_id}/review', json={'decision': 'approved', 'note': '补签'},
                          headers=supervisor)
    assert blocked.status_code == 409

    compute()
    latest = client.get(f'/api/runs/{old["superseded_by"]}', headers=supervisor).json()
    assert latest['status'] == 'succeeded'
    assert latest['version'] == 2
    signed = client.post(f'/api/runs/{latest["id"]}/review',
                         json={'decision': 'approved', 'note': '顶部配法一致'}, headers=supervisor)
    assert signed.status_code == 201, signed.text


def test_failed_retry_does_not_add_version(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = seed_batch(client, analyst, '失败重试批次', count=2)
    run_id = create_run(client, analyst, batch)
    body = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert body['status'] == 'failed'
    assert body['version'] == 1
    retry = client.post(f'/api/runs/{run_id}/retry', headers=analyst)
    assert retry.status_code == 201, retry.text
    assert retry.json()['id'] == run_id and retry.json()['version'] == 1
    compute()
    again = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert again['version'] == 1 and again['status'] == 'failed'
    runs = client.get(f'/api/runs?batch_id={batch}', headers=supervisor).json()
    assert len(runs) == 1

    # fixing the missing segment retries in place rather than adding a version
    response = client.post(f'/api/batches/{batch}/tickets',
                           json={'tickets': [{'code': 'SJ-03-O-01', 'segment': 'SJ-03', 'procedure': 'old', 'kind': 'initial',
                                              'minutes': 26.0, 'inspected_on': '2026-11-10'},
                                             {'code': 'SJ-03-N-01', 'segment': 'SJ-03', 'procedure': 'new', 'kind': 'initial',
                                              'minutes': 26.4, 'inspected_on': '2026-11-10'}]}, headers=analyst)
    assert response.status_code == 201, response.text
    compute()
    runs = client.get(f'/api/runs?batch_id={batch}', headers=supervisor).json()
    assert len(runs) == 1
    assert runs[0]['status'] == 'succeeded'


def test_signed_conclusion_survives_retest_and_new_version(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = seed_batch(client, analyst, '签核后补测批次')
    run_id = create_run(client, analyst, batch)
    signed_metrics = client.get(f'/api/runs/{run_id}', headers=supervisor).json()['result']['metrics']
    signed = client.post(f'/api/runs/{run_id}/review', json={'decision': 'approved', 'note': '通过'},
                         headers=supervisor)
    assert signed.status_code == 201, signed.text

    response = client.post(f'/api/batches/{batch}/tickets', json={'tickets': [
        {'code': 'SJ-02-N-02', 'segment': 'SJ-02', 'procedure': 'new', 'kind': 'retest',
         'minutes': 24.0, 'inspected_on': '2026-11-13'}]}, headers=analyst)
    assert response.status_code == 201, response.text

    old = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert old['status'] == 'succeeded'
    assert old['review']['decision'] == 'approved'
    assert old['stale'] is False
    assert old['superseded_by'] is None
    repro = client.post(f'/api/runs/{run_id}/reproduce', headers=supervisor)
    assert repro.status_code == 200 and repro.json()['matches'] is True
    assert repro.json()['metrics'] == signed_metrics

    compute()
    newer = [run for run in client.get(f'/api/runs?batch_id={batch}', headers=analyst).json()
             if run['version'] == 2]
    assert len(newer) == 1 and newer[0]['status'] == 'succeeded'
    assert newer[0]['review'] is None


def test_disagreeing_configuration_blocks_signature(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    batch = seed_batch(client, analyst, '配法不一致批次', count=8)
    client.post(f'/api/batches/{batch}/tickets', json={'tickets': [
        {'code': 'SJ-05-N-02', 'segment': 'SJ-05', 'procedure': 'new', 'kind': 'retest',
         'minutes': 80.0, 'inspected_on': '2026-11-12'}]}, headers=analyst)
    runs = client.get(f'/api/runs?batch_id={batch}', headers=analyst).json()
    assert runs == []
    run_id = create_run(client, analyst, batch)
    body = client.get(f'/api/runs/{run_id}', headers=supervisor).json()
    assert body['result']['consistent'] is False
    assert body['result']['configurations']['blocking']
    signed = client.post(f'/api/runs/{run_id}/review', json={'decision': 'approved', 'note': '强行通过'},
                         headers=supervisor)
    assert signed.status_code == 409


def test_viewer_only_sees_signed(client):
    analyst = auth(client, 'analyst@demo.local')
    supervisor = auth(client, 'supervisor@demo.local')
    viewer = auth(client, 'viewer@demo.local')
    batch = seed_batch(client, analyst, '只读批次', count=10)
    run_id = create_run(client, analyst, batch)
    listed = client.get('/api/runs', headers=viewer).json()
    assert all(item['review'] for item in listed)
    assert all(item['id'] != run_id for item in listed)
    client.post(f'/api/runs/{run_id}/review', json={'decision': 'approved', 'note': '通过'}, headers=supervisor)
    listed = client.get('/api/runs', headers=viewer).json()
    assert any(item['id'] == run_id for item in listed)
