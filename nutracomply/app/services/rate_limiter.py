"""
Simple rate limiter. Uses Redis if available, falls back to in-memory dict.
Never raises exceptions — if the limiter itself errors, it allows the request through.

Usage:
    limiter = RateLimiter()

    # In a route:
    allowed, retry_after = limiter.check("login", client_ip, limit=5, window=60)
    if not allowed:
        return HTMLResponse("Too many requests", status_code=429)
"""
import time
import threading
from collections import defaultdict
from app.config import get_settings


class RateLimiter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._redis = None
        self._memory: dict = defaultdict(list)  # key -> [timestamp, ...]
        self._mem_lock = threading.Lock()
        self._try_connect_redis()

    def _try_connect_redis(self):
        try:
            import redis as redis_lib
            settings = get_settings()
            r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            r.ping()
            self._redis = r
            print("[rate_limiter] Redis connected")
        except Exception as e:
            print(f"[rate_limiter] Redis unavailable, using in-memory: {e}")
            self._redis = None

    def check(self, namespace: str, identifier: str, limit: int, window: int) -> tuple:
        """
        Returns (allowed: bool, retry_after_seconds: int).
        If the limiter itself errors, returns (True, 0) — fail open.
        """
        try:
            key = f"rl:{namespace}:{identifier}"
            if self._redis:
                return self._check_redis(key, limit, window)
            else:
                return self._check_memory(key, limit, window)
        except Exception as e:
            print(f"[rate_limiter] check error: {e}")
            return True, 0

    def _check_redis(self, key: str, limit: int, window: int) -> tuple:
        now = time.time()
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = pipe.execute()
        count = results[2]
        if count > limit:
            oldest = self._redis.zrange(key, 0, 0, withscores=True)
            retry = int(window - (now - oldest[0][1])) + 1 if oldest else window
            return False, retry
        return True, 0

    def _check_memory(self, key: str, limit: int, window: int) -> tuple:
        now = time.time()
        with self._mem_lock:
            timestamps = [t for t in self._memory[key] if now - t < window]
            timestamps.append(now)
            self._memory[key] = timestamps
            if len(timestamps) > limit:
                retry = int(window - (now - timestamps[0])) + 1
                return False, retry
            return True, 0


# Singleton instance
limiter = RateLimiter()
