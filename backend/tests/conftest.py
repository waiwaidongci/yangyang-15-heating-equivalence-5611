import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

DB = Path(tempfile.mkdtemp()) / 'test.db'
os.environ.setdefault('DATABASE_URL', f'sqlite:///{DB}')
os.environ.setdefault('SEED_DEMO', 'false')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('ARTIFACT_ROOT', tempfile.mkdtemp())


class FakeRedis:
    def __init__(self):
        self.data = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def pipeline(self):
        return self

    def incr(self, key):
        self.data[key] = self.data.get(key, 0) + 1
        return self

    def expire(self, *args, **kwargs):
        return self

    def execute(self):
        return [1, True]

    def set(self, *args, **kwargs):
        return True

    def get(self, *args):
        return 'yes'

    def lpush(self, *args):
        return 1

    def ltrim(self, *args):
        return True

    def blpop(self, *args, **kwargs):
        return None

    def ping(self):
        return True


def install_fake_redis():
    import src.main as main
    import src.routes.session as session_route
    import src.services.broker as broker
    fake = FakeRedis()
    broker.redis = fake
    main.redis = fake
    session_route.redis = fake
    return fake
