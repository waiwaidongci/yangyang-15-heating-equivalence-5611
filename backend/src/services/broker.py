from redis import Redis
from redis.exceptions import RedisError

from src.config.runtime import REDIS


redis = Redis.from_url(REDIS, socket_connect_timeout=2, socket_timeout=3, decode_responses=True)


def wake_worker():
    try:
        with redis.pipeline() as channel:
            channel.lpush('desk:wake', 'new')
            channel.ltrim('desk:wake', 0, 31)
            channel.execute()
    except RedisError:
        # The relational database is authoritative. The worker also polls it.
        pass
