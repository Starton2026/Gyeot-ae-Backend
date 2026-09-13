"""시간(KST)·거리·방위 계산 헬퍼."""
import math
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)


def parse_dt(s):
    """ISO 8601 문자열 → aware datetime. 오프셋 없으면 KST로 간주."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def elapsed_minutes(iso_str):
    """해당 시각부터 지금까지 경과 분 (서버 시각 기준)."""
    return max(0, int((now_kst() - parse_dt(iso_str)).total_seconds() // 60))


def haversine_km(lat1, lng1, lat2, lng2):
    """두 좌표 간 거리(km)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def bearing_8(lat1, lng1, lat2, lng2):
    """이전 좌표 → 현재 좌표의 8방위 문자열."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return _DIRS[int((deg + 22.5) // 45) % 8]
