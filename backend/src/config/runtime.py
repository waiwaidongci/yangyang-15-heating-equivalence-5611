import os
from pathlib import Path

DSN = os.environ.get('DATABASE_URL', 'postgresql+psycopg://desk:desk-local@db/desk')
REDIS = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
JWT_SECRET = os.environ.get('JWT_SECRET', 'desk-local-demo-token-do-not-use-externally')
WORKDIR = Path(os.environ.get('ARTIFACT_ROOT', '/artifacts'))
SEED_DEMO = os.environ.get('SEED_DEMO', 'true').lower() == 'true'
