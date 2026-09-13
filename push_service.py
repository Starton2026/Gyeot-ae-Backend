"""FCM 푸시 발송 — 주변 시민 알림과 제보자 결과 알림.

serviceAccountKey.json이 있을 때만 실제로 보낸다. 없으면 조용히 0을 돌려준다.
**키가 없다고 실종자 등록이나 발견 완료가 실패하면 안 된다.** 사건 기록이
본체고 알림은 곁다리다.

firebase_admin은 firebase_service가 초기화해 둔 기본 앱을 그대로 쓴다.
serviceAccountKey.json 하나로 Firestore 관제 연동과 푸시가 함께 산다.

카카오 푸시를 쓰지 않는 이유: 카카오도 안드로이드 인증에 Firebase 서비스 계정
키를 요구해서 Firebase를 어차피 만들어야 하고, 대상 지정이 사용자 ID 단위다.
우리 알림의 주 대상은 로그인하지 않은 주변 시민이라(설계 결정 1번) ID가 없다.
"""
from datetime import time as clock

import db as database
import firebase_service
from utils import haversine_km, now_kst

# 한 번에 보낼 수 있는 토큰 수 (FCM 멀티캐스트 상한).
_BATCH = 500

# 기기가 반경을 안 정했을 때 쓰는 값. 명세서 4)의 선택지 가운데 기본값이다.
DEFAULT_RADIUS_KM = 5

_messaging = None
if firebase_service.is_enabled():
    try:
        from firebase_admin import messaging as _messaging
    except ImportError:  # requirements에는 있지만 안 깔린 환경
        print("[push] firebase-admin이 없어 푸시를 보내지 않습니다.")


def is_enabled():
    """실제로 보낼 수 있는 상태인지."""
    return _messaging is not None


# ── 누구에게 보낼지 ──────────────────────────────────────

def _in_quiet_hours(quiet, at):
    """방해 금지 시간 안인지. 자정을 넘는 구간(23:00~07:00)도 처리한다."""
    if not quiet:
        return False
    start, end = quiet.get("from"), quiet.get("to")
    if not start or not end:
        return False
    try:
        start, end = clock.fromisoformat(start), clock.fromisoformat(end)
    except ValueError:  # 형식이 틀리면 조용히 무시한다. 알림을 막지는 않는다.
        return False

    now = at.time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _wants(device, missing, at):
    """이 기기가 이 사건 알림을 받기로 했는지.

    구분(아동·어르신)을 안 고른 기기는 전부 받는 것으로 본다. 빈 목록을
    "아무것도 안 받음"으로 읽으면, 설정을 건드린 적 없는 사람이 알림을 하나도
    못 받는다.
    """
    if not device.get("push_token"):
        return False

    categories = device.get("categories")
    if categories and missing.get("category") not in categories:
        return False

    if _in_quiet_hours(device.get("quiet_hours"), at):
        return False

    # 위치를 모르는 기기는 건너뛴다. 반경을 지킬 수 없는데 보내면, 서울 사람이
    # 부산 사건 알림을 받고 알림 자체를 꺼 버린다.
    lat, lng = device.get("lat"), device.get("lng")
    if lat is None or lng is None:
        return False

    radius = device.get("radius_km") or DEFAULT_RADIUS_KM
    distance = haversine_km(missing["last_lat"], missing["last_lng"], lat, lng)

    return distance <= radius


# ── 보내기 ──────────────────────────────────────────────

def _is_stale(error):
    """더는 살아 있지 않은 토큰인지. 앱을 지웠거나 토큰이 갱신된 경우."""
    if error is None:
        return False
    if _messaging is not None and isinstance(error, _messaging.UnregisteredError):
        return True

    return type(error).__name__ in ("UnregisteredError", "SenderIdMismatchError")


def _send(tokens, title, body, data):
    """(보낸 수, 죽은 토큰 목록)."""
    if not tokens or _messaging is None:
        return 0, []

    sent, stale = 0, []
    for start in range(0, len(tokens), _BATCH):
        chunk = tokens[start:start + _BATCH]
        message = _messaging.MulticastMessage(
            tokens=chunk,
            notification=_messaging.Notification(title=title, body=body),
            # 값은 전부 문자열이어야 한다. 숫자를 그대로 넣으면 FCM이 거부한다.
            data={k: str(v) for k, v in data.items()},
            # 실종 알림은 골든타임이 걸린 알림이다. 절전 모드에서도 깨운다.
            android=_messaging.AndroidConfig(priority="high"),
        )
        try:
            result = _messaging.send_each_for_multicast(message)
        except Exception as error:  # 알림 장애가 본 API를 죽이면 안 된다
            print(f"[push] 발송 실패: {error}")
            continue

        sent += result.success_count
        for token, response in zip(chunk, result.responses):
            if not response.success and _is_stale(response.exception):
                stale.append(token)

    return sent, stale


def _drop_stale(db, tokens):
    """죽은 토큰을 지운다. 기기 기록은 남기고 토큰만 비운다.

    기기를 통째로 지우면 반경·구분 설정까지 사라져서, 앱이 새 토큰을 올릴 때
    사용자가 정한 값이 기본값으로 되돌아간다.
    """
    if not tokens:
        return

    dead = set(tokens)
    for device in db.get("devices", []):
        if device.get("push_token") in dead:
            device["push_token"] = None
    database.save_db(db)


# ── 바깥에서 부르는 것 ───────────────────────────────────

def notify_new_case(db, missing, exclude_device_hash=None):
    """반경 안 기기에 새 실종 신고를 알린다. 실제로 보낸 기기 수를 돌려준다.

    등록한 보호자 본인의 기기는 뺀다. 방금 폼을 채운 사람에게 "내 주변에서
    실종 신고가 있었어요"를 보내면 알림이 장난처럼 보인다.
    """
    at = now_kst()
    targets = [
        device
        for device in db.get("devices", [])
        if device.get("device_hash") != exclude_device_hash
        and _wants(device, missing, at)
    ]
    if not targets:
        return 0

    age = missing.get("age")
    where = missing.get("last_address") or "마지막 목격 위치 확인"
    sent, stale = _send(
        [device["push_token"] for device in targets],
        "내 주변에서 실종 신고가 있었어요",
        f"{missing['name']} · {age}세 · {where}",
        {"type": "missing", "missing_id": missing["id"]},
    )
    _drop_stale(db, stale)

    return sent


def notify_resolved(db, missing, reporter_keys):
    """제보한 사람들에게 결과를 알린다. 실제로 보낸 기기 수를 돌려준다.

    **재참여 동기를 만드는 유일한 지점이다**(명세서 10). 내 제보가 어떻게
    됐는지 끝내 모르면 다음 제보를 하지 않는다.

    [reporter_keys]는 회원번호와 기기 해시가 섞인 집합이다. 제보는 로그인
    없이도 할 수 있어서(설계 결정 1번) 제보자가 계정으로 식별되지 않는다.
    """
    if not reporter_keys:
        return 0

    keys = set(reporter_keys)
    guardian_id = missing.get("guardian_id")
    tokens = [
        device["push_token"]
        for device in db.get("devices", [])
        if device.get("push_token")
        # 보호자 본인이 발견 완료를 눌렀다. 자기가 누른 결과를 알림으로 다시
        # 받을 이유가 없다.
        and device.get("user_id") != guardian_id
        and (
            device.get("device_hash") in keys
            or (device.get("user_id") and device["user_id"] in keys)
        )
    ]
    if not tokens:
        return 0

    sent, stale = _send(
        # 중복 제거. 한 기기가 같은 사건에 여러 번 제보했을 수 있다.
        list(dict.fromkeys(tokens)),
        "찾았습니다",
        f"제보해 주신 {missing['name']} 님을 찾았어요. 고맙습니다.",
        {"type": "resolved", "missing_id": missing["id"]},
    )
    _drop_stale(db, stale)

    return sent
