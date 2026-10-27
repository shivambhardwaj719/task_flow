import logging
from typing import Optional
import redis
from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Return a singleton Redis client instance or None if unreachable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0
            )
            _redis_client.ping()
        except Exception as e:
            logger.warning("Redis is not available at %s: %s", settings.REDIS_URL, str(e))
            return None
    return _redis_client
