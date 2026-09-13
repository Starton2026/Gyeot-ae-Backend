"""카카오 로그인 + 자체 토큰 발급/검증.

흐름:
1. 프론트가 카카오 SDK(JavaScript 키)로 로그인해 access_token을 받는다
2. POST /auth/kakao 로 access_token을 보내면, 서버가 카카오 API에 검증한다
3. 처음 보는 kakao_id면 그 자리에서 계정 생성 (가입/로그인 구분 없음)
4. 서버 자체 토큰(itsdangerous 서명)을 발급 → 이후 Authorization: Bearer <token>

백엔드에는 카카오 키가 필요 없다. 받는 정보는 닉네임·프로필 이미지뿐.
"""
import os

import requests
from itsdangerous import BadSignature, URLSafeTimedSerializer

KAKAO_ME_URL = "https://kapi.kakao.com/v2/user/me"
TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7일

# 데모용 기본값. 실서비스면 반드시 환경변수로 교체 (SECRET_KEY=... python app.py)
_serializer = URLSafeTimedSerializer(
    os.environ.get("SECRET_KEY", "gyeot-ae-hackathon-secret"), salt="auth"
)


def verify_kakao_token(access_token):
    """카카오 access_token 검증 → {kakao_id, name, profile_image_url} 또는 None."""
    try:
        res = requests.get(
            KAKAO_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5,
        )
    except requests.RequestException:
        return None
    if res.status_code != 200:
        return None
    data = res.json()
    props = data.get("properties") or {}
    return {
        "kakao_id": str(data["id"]),
        "name": props.get("nickname") or "사용자",
        "profile_image_url": props.get("profile_image"),  # 없을 수 있음(None)
    }


def issue_token(user_id):
    """자체 토큰 발급."""
    return _serializer.dumps(user_id)


def user_id_from_token(token):
    """토큰 → user_id. 유효하지 않으면 None."""
    try:
        return _serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except BadSignature:
        return None


def current_user_id(request):
    """Authorization: Bearer <token> 헤더에서 user_id 추출. 없으면 None."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return user_id_from_token(header[7:].strip())
