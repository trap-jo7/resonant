import logging
import os
import secrets
import redis
from fastapi import Depends, HTTPException, Request, Response
from resonant_common.config import settings

log = logging.getLogger("resonant.security")
COOKIE = "resonant_sid"
_redis = redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True)


def redis_client():
    return _redis


def session_id(request: Request, response: Response) -> str:
    """Anonymous, httpOnly session. Identity always comes from this cookie, never from request bodies."""
    sid = request.cookies.get(COOKIE)
    if not sid or len(sid) < 20:
        sid = secrets.token_urlsafe(24)
        response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=7 * 86400,
                            secure=os.environ.get("COOKIE_SECURE", "false") == "true", path="/")
    return sid


def client_ip(request: Request) -> str:
    # Behind a trusted proxy, configure uvicorn --proxy-headers/--forwarded-allow-ips so this is the real IP.
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int, window_s: int, fail_closed: bool = False):
    def dep(request: Request):
        key = f"rl:{bucket}:{client_ip(request)}"
        try:
            n = _redis.incr(key)
            if n == 1:
                _redis.expire(key, window_s)
            if n > limit:
                raise HTTPException(429, "Too many requests. Please wait and try again.",
                                    headers={"Retry-After": str(window_s)})
        except redis.RedisError:
            log.warning("rate limiter unavailable")
            if fail_closed:
                raise HTTPException(503, "Service temporarily unavailable.")
    return Depends(dep)
