"""얼굴대조 AI 로직 (face_recognition / dlib 기반).

등급 체계 (API 명세서 7절 · 기능정의서 5.2):
- high    : similarity >= 70   → route_index 부여
- medium  : 40 <= s < 70       → route_index 부여
- low     : s < 40             → 저장하되 경로 제외
- no_face : 얼굴 미검출        → 저장하되 경로 제외 (에러 아님)
"""
import face_recognition
import numpy as np
from PIL import Image, ImageOps

# high 등급 기준. 명세서가 정한 값이다.
#
# 실측에서는 동일 인물 정면 사진이 65.4%로 나와 이 선에 못 미친 적이 있다.
# 그래도 명세를 따른다 — 앱과 서버가 같은 기준을 써야 화면의 "높음"과 서버의
# 판단이 어긋나지 않는다. 기준을 바꿔야 한다면 명세부터 고친다.
SIMILARITY_HIGH = 70
SIMILARITY_ROUTE = 40  # 경로(route_index) 포함 기준


# 검출 전에 긴 변을 이만큼으로 줄인다. 폰 원본(1600~3000px)을 그대로 넣으면 HOG
# 검출이 한 장에 5~15초 걸린다. 이 크기에서도 한 사람 얼굴은 검출 하한(약 80px)을
# 넉넉히 넘는다.
_DETECT_MAX_SIDE = 1024


def _load_upright(path):
    """사진을 **EXIF 회전값대로 세워서** 줄여 읽는다.

    폰 카메라는 픽셀을 가로로 저장하고 "90도 돌려서 보라"는 값만 붙인다.
    `face_recognition.load_image_file`은 그 값을 무시해서, 세로로 찍은 사진의
    얼굴이 옆으로 누운 채 검출기에 들어가 거의 못 찾았다(실기기 2026-09-14,
    회전값 6인 사진이 전부 no_face).
    """
    with Image.open(path) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
        upright.thumbnail((_DETECT_MAX_SIDE, _DETECT_MAX_SIDE))
        return np.array(upright)


def get_face_encoding(path):
    """사진 경로 → 128차원 얼굴 인코딩 벡터. 얼굴이 없으면 None.

    여러 명이 찍혔으면 **가장 큰 얼굴**을 쓴다 — 첫 번째 얼굴은 뒤에 지나가던
    사람일 수 있다.

    사진을 90도씩 돌려 다시 찾는 것은 하지 않는다. 실측에서 느려지기만 하고,
    돌려서 찾은 얼굴은 어느 사건과도 30% 안팎이라 오검출이었다.
    """
    # 가짜 모듈(hackerton/fake-face)은 사진 내용을 해시할 뿐 검출기가 없다.
    if not hasattr(face_recognition, "face_locations"):
        encodings = face_recognition.face_encodings(face_recognition.load_image_file(path))
        return encodings[0] if encodings else None

    image = _load_upright(path)
    locations = face_recognition.face_locations(image)
    if not locations:
        return None
    largest = max(locations, key=lambda box: (box[2] - box[0]) * (box[1] - box[3]))
    encodings = face_recognition.face_encodings(image, known_face_locations=[largest])
    return encodings[0] if encodings else None


def best_similarity(known_encodings, path):
    """등록 사진 인코딩들(여러 장)과 제보 사진을 비교해 최고 유사도 채택.

    returns: (similarity float|None, face_found bool, best_photo_index int|None)
    - 유사도% = (1 - face_distance) * 100, 소수 1자리 반올림
    """
    report_encoding = get_face_encoding(path)
    if report_encoding is None:
        return None, False, None

    distances = face_recognition.face_distance(
        np.array(known_encodings), report_encoding
    )
    best = int(np.argmin(distances))
    similarity = round(max(0.0, float(1 - distances[best])) * 100, 1)
    return similarity, True, best


def grade_of(similarity, face_found):
    """유사도 → 등급 문자열."""
    if not face_found:
        return "no_face"
    if similarity >= SIMILARITY_HIGH:
        return "high"
    if similarity >= SIMILARITY_ROUTE:
        return "medium"
    return "low"
