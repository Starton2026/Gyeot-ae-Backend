# 🧡 곁애 (Gyeot-ae)

> **실종 아동·치매노인 조기 발견 네트워크**
> "곁에 있다 + 사랑" — 시민의 눈이 모여 실종자의 골든타임을 지킵니다.

---

## 📌 어떤 서비스인가요?

실종자(아동·치매노인)가 발생하면, 시민이 목격 사진을 제보합니다.
**AI가 실종자 원본 사진과 얼굴을 대조**해 진짜 후보만 걸러내고, 매칭된 제보들을 **시간순 위치로 이어 이동 경로를 지도에 그려줍니다.**

```
보호자: 실종 신고 등록 (사진 + 인상착의 + 마지막 위치)
   ↓
시민: 목격 사진 제보 (사진 + GPS 자동 첨부)
   ↓
AI: 얼굴대조 → 유사도 % 계산 → 60% 이상이면 매칭!
   ↓
관제: 매칭된 제보를 시간순으로 연결 → 이동 경로 시각화 🗺️
```

### 다른 서비스와 뭐가 다른가요?

| 차별점 | 설명 |
|---|---|
| 🗺️ **이동 경로 추적** | 단순 제보 게시판이 아니라, 제보를 시간순으로 이어 실종자의 동선을 추정 |
| 🔄 **양방향 소통** | 재난문자(앰버경보)는 일방향이지만, 곁애는 시민이 되돌려 제보 |
| 🤖 **AI 필터링** | 얼굴대조로 수많은 제보 중 진짜 후보만 골라냄 (사람이 최종 확인) |

### 사용자 역할

- **보호자** — 실종 신고를 등록합니다
- **시민(목격자)** — 주변 실종 알림을 보고, 목격하면 사진+위치를 제보합니다
- **관제(경찰/보호자)** — 들어온 제보를 지도와 타임라인으로 보며 경로를 추적합니다

> 해커톤 데모 범위에서는 로그인 없이 역할별 화면 진입만 구분합니다.

---

## 🛠️ 기술 스택

모두 **무료, 카드 등록 불필요**로 구성했습니다.

| 영역 | 기술 | 비고 |
|---|---|---|
| 백엔드 | **Python 3.10+ / Flask** | 가볍고 빠른 API 서버 |
| 얼굴대조 AI | **face_recognition** (dlib 기반) | 로컬에서 무료로 동작, 128차원 얼굴 벡터 비교 |
| 저장소 | **JSON 파일 DB** (`db.json`) + `uploads/` 폴더 | 해커톤용. 실서비스는 PostgreSQL 등으로 교체 |
| 실시간 푸시 | **Firestore** (firebase-admin) | 제보가 들어오는 순간 관제 지도에 실시간 반영 (선택) |
| CORS | **flask-cors** | 프론트가 다른 오리진에서 자유롭게 호출 |
| 외부 공개 | **ngrok** | 데모 시 임시 공개 URL 발급 |
| 프론트(별도 레포) | React / Vanilla JS + **카카오맵 SDK** | 폴리라인으로 이동 경로 표시 |

### AI 얼굴대조 원리

1. 실종자 등록 시 사진(여러 장)에서 **128차원 얼굴 특징 벡터**를 추출해 전부 저장
2. 제보 사진이 들어오면 각 벡터와 **유클리드 거리**를 계산해 **최고 유사도 채택**
3. `유사도(%) = (1 - 거리) × 100` → 등급 부여

| 등급 | 구간 | 경로(route_index) |
|---|---|---|
| `high` | 60% 이상 | 부여 |
| `medium` | 40 ~ 60% | 부여 |
| `low` | 40% 미만 | 제외 (저장은 함) |
| `no_face` | 얼굴 미검출 | 제외 (에러 아님 — 저장) |

**모든 제보를 저장합니다.** 임계값은 표시 등급과 경로 포함 여부만 결정합니다.

---

## 📁 폴더 구조

```
Gyeot-ae-Backend/
├── app.py              # Flask 엔트리 + API 라우팅
├── face_service.py     # 얼굴대조 AI (다중 인코딩 비교, 등급제)
├── db.py               # JSON DB 읽기/쓰기 헬퍼
├── utils.py            # KST 시각·거리·방위 계산
├── firebase_service.py # Firestore 실시간 푸시 (키 있으면 자동 활성화)
├── seed.py             # 데모용 시드 데이터 생성 스크립트
├── requirements.txt    # 의존성 목록
├── uploads/            # 업로드된 사진 (git 제외)
├── db.json             # 데이터 파일 (git 제외)
└── README.md           # 이 문서
```

---

## 🚀 설치 & 실행

```bash
# macOS: dlib 빌드에 cmake 필요
brew install cmake

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # dlib 빌드에 몇 분 걸릴 수 있어요

python app.py                     # → http://localhost:5001
```

> ⚠️ dlib 설치가 실패하면 `pip install cmake` 후 재시도, 그래도 안 되면 conda 환경을 사용하세요.
> ⚠️ macOS의 5000번 포트는 AirPlay가 점유하는 경우가 많아 **5001번**을 사용합니다.

**데모 시 외부 공개** (프론트에 URL 전달):

```bash
ngrok http 5001
```

**시드 데이터** (실종자 1명 등록 후, 가짜 제보 5건으로 경로 생성):

```bash
python seed.py
```

---

## 🔥 Firestore 실시간 연동 (선택)

제보가 접수되는 **순간** 관제 지도에 핀이 찍히게 하려면 Firestore를 연결하세요.
키 파일이 없으면 자동으로 꺼지고 JSON DB만으로 동작합니다 (데모에 지장 없음).

### 백엔드 설정 (1회)

1. [Firebase 콘솔](https://console.firebase.google.com) → 프로젝트 생성 (Spark 무료 요금제, 카드 불필요)
2. 빌드 → **Firestore Database** → 데이터베이스 만들기 (테스트 모드)
3. ⚙️ 프로젝트 설정 → **서비스 계정** → "새 비공개 키 생성" → 다운로드
4. 받은 JSON을 프로젝트 루트에 **`serviceAccountKey.json`** 이름으로 저장
5. 서버 재시작 → 로그에 `[firebase] Firestore 연동 활성화` 확인

ngrok 사용 시 사진 URL이 올바르게 기록되도록:

```bash
BASE_URL=https://xxxx.ngrok.io python app.py
```

### 데이터 구조

| 컬렉션 | 문서 | 주요 필드 |
|---|---|---|
| `missing/{missing_id}` | 실종자 | name, age, category, last_lat/lng, missing_at, status, photo_urls[], thumbnail_url |
| `reports/{report_id}` | 제보 | missing_id, lat, lng, place_name, observed_at, similarity, grade, route_index, photo_url |

### 프론트(관제 화면) 구독 예시

```js
import { collection, query, where, orderBy, onSnapshot } from "firebase/firestore";

const q = query(
  collection(db, "reports"),
  where("missing_id", "==", missingId),
  orderBy("observed_at")
);
onSnapshot(q, (snap) => {
  const reports = snap.docs.map((d) => d.data());
  // route_index가 있는 제보만 시간순 폴리라인으로, 나머지는 회색 핀으로.
  // 새 제보가 오면 이 콜백이 자동 호출됨 → 핀이 실시간으로 추가!
});
```

> ⚠️ `where + orderBy` 조합은 Firestore **복합 인덱스**가 필요합니다. 첫 실행 시 에러 메시지에 뜨는 링크를 클릭하면 자동 생성됩니다 — 데모 전에 미리 한 번 실행해두세요.
>
> Firebase를 안 쓰는 경우: 관제 화면에서 `GET /missing/{id}/reports`를 2~3초마다 폴링해도 데모에는 충분합니다.

---

## 📡 API 명세

> 2026-09-12 디자인 확정본 기준. 상세 스키마는 API 명세서 문서 참조.
> 모든 시각은 ISO 8601 + KST 오프셋 (`2026-09-13T14:40:00+09:00`).
> 게스트 요청은 `X-Device-Hash` 헤더 권장 (제보 남용 방지 기준).

### 한눈에 보기

| # | 메서드 | 경로 | 역할 | 화면 |
|---|---|---|---|---|
| 1 | `POST` | `/missing` | 실종자 등록 (사진 다중) | S7 |
| 2 | `GET` | `/missing` | 목록 (검색·필터·정렬·긴급도) | S1·S2·S5 |
| 3 | `GET` | `/missing/{id}` | 상세 | S3 |
| 4 | `POST` | `/reports/analyze` | **사진 분석** (제보 전 단계) | S4-1 |
| 5 | `POST` | `/reports` | **제보 확정** | S4 |
| 6 | `GET` | `/missing/{id}/reports` | 제보 목록 + 경로 + 슬라이더 | S3·S5 |
| 7 | `GET` | `/uploads/{filename}` | 사진 서빙 (`{이름}_thumb.jpg` 썸네일) | 공통 |

구 API(`POST /report`, `GET /reports/{id}`)는 하위 호환 어댑터로 유지됩니다.

### 에러 포맷 (공통)

```json
{ "error": { "code": "FACE_NOT_FOUND", "message": "...", "field": "photos" } }
```

`VALIDATION_ERROR`(400) · `FACE_NOT_FOUND`(400, 등록만) · `NOT_FOUND`(404) · `ANALYSIS_EXPIRED`(410) · `RATE_LIMITED`(429)

### 1) 실종자 등록

`POST /missing` (multipart/form-data)

| 필드 | 필수 | 설명 |
|---|---|---|
| `name`, `last_lat`, `last_lng`, `photos[]` | O | 사진 다중 — 첫 장이 대표 |
| `age`, `gender`, `category`, `description`, `missing_at`, `guardian_phone` | 권장 | `category`: child/elderly/other |
| `last_address`, `height_cm`, `weight_kg` | X | |

```bash
curl -X POST http://localhost:5001/missing \
  -F "name=김하준" -F "age=7" -F "gender=male" -F "category=child" \
  -F "description=노란 후드티, 검정 백팩" \
  -F "last_lat=37.4491" -F "last_lng=126.7312" \
  -F "missing_at=2026-09-13T14:40:00+09:00" -F "guardian_phone=010-0000-0000" \
  -F "photos=@face1.jpg" -F "photos=@face2.jpg"
```

응답 `201`: `{ id, name, photos[], face_encoding_count, notified_devices }`
모든 사진에서 얼굴 미검출 시 `400 FACE_NOT_FOUND`.

### 2) 실종자 목록

`GET /missing?q=&category=all&status=active&sort=urgency&lat=&lng=&radius_km=&cursor=0&limit=20`

- `sort`: `urgency`(기본) / `recent` / `distance`
- `lat`/`lng` 전달 시 `distance_km` 포함, 긴급도의 거리 가중치 반영
- 응답: `{ count, next_cursor, items:[{ id, name, age, thumbnail, elapsed_minutes, urgency_score, urgency_level, report_count, ... }] }`
- `elapsed_minutes`는 서버 시각 기준 계산 (클라이언트 계산 금지)

### 3) 실종자 상세

`GET /missing/{id}` → 기본 정보 + `photos[]`, `elapsed_minutes`, `report_count`, `match_count`

### 4) 사진 분석 ★ (제보 전 단계)

`POST /reports/analyze` (multipart: `missing_id`, `photo`)

```json
{
  "analysis_id": "an_7x9k2m",
  "similarity": 63.4, "grade": "high", "face_found": true,
  "photo_url": "/uploads/tmp/an_7x9k2m.jpg",
  "matched_photo_url": "/uploads/m_xxx_1.jpg",
  "expires_at": "2026-09-13T15:10:00+09:00"
}
```

- 얼굴 미검출은 **에러가 아님** — `similarity: null, grade: "no_face"`로 응답, 제보 가능
- 임시 사진은 `uploads/tmp/`, **TTL 10분** (만료 시 자동 삭제)
- `matched_photo_url`: 여러 등록 사진 중 최고 유사도를 낸 사진

### 5) 제보 확정 ★

`POST /reports` (application/json)

```json
{ "analysis_id": "an_7x9k2m", "lat": 37.4622, "lng": 126.7401,
  "place_name": "만수주공 앞 버스정류장", "observed_at": "2026-09-13T17:12:00+09:00" }
```

응답 `201`: `{ id, missing_id, similarity, grade, route_index, photo_url, observed_at, created_at, guardian_notified }`

- `observed_at`(목격 시각, 경로 정렬 기준)과 `created_at`(전송 시각)은 분리
- `route_index`는 유사도 40% 이상만 부여, 미만은 `null`
- 분석 만료 시 `410 ANALYSIS_EXPIRED`
- 게스트 제한: 사건 1건당 `X-Device-Hash` 기준 10분 내 3회 → 초과 시 `429`

### 6) 제보 목록 / 이동 경로 ★

`GET /missing/{id}/reports?min_similarity=0&include_low=true&until=`

```json
{
  "count": 6, "hidden_count": 0,
  "origin": { "lat": ..., "lng": ..., "address": "...", "at": "..." },
  "reports": [ { "route_index": 3, "grade": "high", "gap_minutes": 42,
                 "bearing": "SE", "distance_from_prev_km": 1.4, ... } ],
  "path": [ { "lat": ..., "lng": ..., "at": "...", "index": 0, "origin": true }, ... ],
  "time_range": { "from": "...", "to": "...", "ticks": [...] }
}
```

- `reports`는 **최신순** (타임라인용), `path`는 **시간순** + 최초 실종 지점 포함 (폴리라인용) — 방향이 반대인 것은 의도된 것
- `until`: 시간 슬라이더 — 해당 시각까지의 제보만
- `min_similarity=60`: 지도·타임라인 필터 토글용 (`hidden_count`에 숨긴 건수)

### 7) 사진 서빙

`GET /uploads/{filename}` — 썸네일은 `{이름}_thumb.jpg` 규칙 (목록에서는 썸네일 사용)

## 🎬 데모 시나리오

1. 보호자 화면에서 실종자 1명 등록 → `missing_id` 확보
2. 제보 화면에서 서로 다른 위치의 목격 사진을 순차 제보
3. 관제 지도로 전환 → 핀이 시간순으로 찍히고 **경로가 선으로 그려짐**
4. 하이라이트: "유사도 92% 일치!" 뜨는 순간 + 경로 애니메이션

**성공 기준**: "제보 사진 업로드 → 유사도 %가 뜨고 → 지도에 시간순 경로가 그려진다" 이 흐름이 끊김 없이 한 번 돌면 성공.

---

## 🔒 프라이버시

- 제보 사진은 대조 후 삭제하는 것을 원칙으로 설계 (활성 신고 건에만 수집)
- AI는 "후보 순위 제시" 역할이며, 최종 확인은 사람이 합니다
