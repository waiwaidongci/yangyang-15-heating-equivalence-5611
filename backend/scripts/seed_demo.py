import json
from datetime import date, timedelta

from sqlalchemy import func, select

from src.domain.analysis import seed as seed_differences
from src.models.base import Base, Session, engine
from src.models.workflow import AnalysisRun, Batch, Review, Schedule, Ticket
from src.services.tickets import clean_ticket


DEMO_BATCH = 'SJ-2611-并行巡检'


def seed_tickets(db):
    """Two 32-segment CSV equivalents (one per procedure), no duplicates on rerun."""
    existing = db.scalar(select(Batch.id).where(Batch.name == DEMO_BATCH))
    if existing:
        return 0
    batch = Batch(name=DEMO_BATCH, note='2026-11-09 至 11-16 试点批次（演示）', created_by='analyst@demo.local')
    db.add(batch)
    db.flush()
    start = date(2026, 11, 9)
    items = []
    for i, difference in enumerate(seed_differences()):
        old = round(24 + (7 * i % 15) * 0.8, 2)
        day = (start + timedelta(days=i // 4)).isoformat()
        segment = f'SJ-{i + 1:02d}'
        items.append(clean_ticket({'code': f'{segment}-O-01', 'segment': segment, 'kind': 'initial',
                                   'minutes': old, 'inspected_on': day}, 'old'))
        items.append(clean_ticket({'code': f'{segment}-N-01', 'segment': segment, 'kind': 'initial',
                                   'minutes': round(old + difference, 2), 'inspected_on': day}, 'new'))
    db.add_all([Ticket(batch_id=batch.id, code=row['code'], segment=row['segment'],
                       procedure=row['procedure'], kind=row['kind'], minutes=row['minutes'],
                       target_code=row['target_code'], inspected_on=date.fromisoformat(row['inspected_on']),
                       note=row['note'], submitted_by='analyst@demo.local') for row in items])
    db.flush()
    return len(items)


def seed_data():
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        added = seed_tickets(db)
        db.flush()
        counts = {model.__tablename__: db.scalar(select(func.count(model.id)))
                  for model in (Batch, Ticket, AnalysisRun, Review, Schedule)}
        counts['seeded_tickets'] = added
        return counts


if __name__ == '__main__':
    print(json.dumps(seed_data(), sort_keys=True))
