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

1. 실종자 등록 시 사진에서 **128차원 얼굴 특징 벡터**를 1회 추출해 저장
2. 제보 사진이 들어오면 벡터 간 **유클리드 거리**를 계산
3. `유사도(%) = (1 - 거리) × 100`, **60% 이상이면 매칭**으로 판단

---

## 📁 폴더 구조

```
Gyeot-ae-Backend/
├── app.py              # Flask 엔트리 + API 라우팅
├── face_service.py     # 얼굴대조 AI (인코딩 추출/비교, 임계값 60%)
├── db.py               # JSON DB 읽기/쓰기 헬퍼
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
| `missing/{missing_id}` | 실종자 | name, description, last_lat/lng, photo_url, status |
| `reports/{report_id}` | 제보 | missing_id, lat, lng, similarity, is_match, photo_url, reported_at, timestamp |

### 프론트(관제 화면) 구독 예시

```js
import { collection, query, where, orderBy, onSnapshot } from "firebase/firestore";

const q = query(
  collection(db, "reports"),
  where("missing_id", "==", missingId),
  where("is_match", "==", true),
  orderBy("timestamp")
);
onSnapshot(q, (snap) => {
  const reports = snap.docs.map((d) => d.data());
  // reports를 시간순으로 폴리라인 + 핀으로 그리면 끝.
  // 새 제보가 오면 이 콜백이 자동 호출됨 → 핀이 실시간으로 추가!
});
```

> Firebase를 안 쓰는 경우: 관제 화면에서 `GET /reports/<id>?only_match=1`을 2~3초마다 폴링해도 데모에는 충분합니다.

---

## 📡 API 명세

Base URL: 로컬 `http://localhost:5001`, 데모는 ngrok URL.
업로드는 모두 `multipart/form-data`이며 CORS가 열려 있습니다.

### 한눈에 보기

| # | 메서드 | 경로 | 역할 | 사용 화면 |
|---|---|---|---|---|
| 1 | `POST` | `/missing` | 실종자 등록 | 보호자 — 실종 등록 |
| 2 | `POST` | `/report` | 제보 접수 + **얼굴대조 실행** | 시민 — 제보하기 |
| 3 | `GET` | `/reports/<missing_id>` | 제보 목록/이동 경로 | 관제 — 지도 |
| 4 | `GET` | `/missing` | 실종자 목록 | 시민 — 홈 |
| 5 | `GET` | `/uploads/<filename>` | 사진 서빙 | 공통 |

### 1) 실종자 등록 — 보호자

`POST /missing` (form-data)

| 필드 | 타입 | 예시 |
|---|---|---|
| `name` | string | `"김순자"` |
| `description` | string | `"빨간 패딩, 검은 바지, 70대 여성"` |
| `last_lat` / `last_lng` | number | `37.5665` / `126.9780` |
| `photo` | file | 실종자 사진 (얼굴 잘 보이게) |

```json
// 성공
{ "message": "실종자 등록 완료", "missing_id": "ab12cd34", "name": "김순자" }
// 실패 400
{ "error": "사진에서 얼굴을 찾지 못했습니다. 얼굴이 잘 보이는 사진을 올려주세요." }
```

```bash
curl -X POST http://localhost:5001/missing \
  -F "name=김순자" -F "description=빨간 패딩, 70대 여성" \
  -F "last_lat=37.5665" -F "last_lng=126.9780" \
  -F "photo=@face.jpg"
```

### 2) 제보 접수 — 시민 ★ 얼굴대조 실행 지점

`POST /report` (form-data)

| 필드 | 타입 | 예시 |
|---|---|---|
| `missing_id` | string | `"ab12cd34"` |
| `lat` / `lng` | number | GPS 자동 첨부 |
| `photo` | file | 목격 사진 |

```json
{
  "message": "김순자님과 유사한 인물이 제보되었습니다!",
  "report_id": "ef56gh78",
  "similarity": 88.5,
  "face_found": true,
  "is_match": true,
  "alert": true
}
```

```bash
curl -X POST http://localhost:5001/report \
  -F "missing_id=ab12cd34" \
  -F "lat=37.5700" -F "lng=126.9820" \
  -F "photo=@sighting.jpg"
```

### 3) 제보 목록 / 이동 경로 — 관제 지도 ★ 데모의 얼굴

`GET /reports/<missing_id>?only_match=1` (`only_match=1`이면 매칭된 제보만)

```json
{
  "missing_id": "ab12cd34",
  "count": 2,
  "reports": [
    { "id": "...", "lat": 37.57, "lng": 126.98, "photo": "report_x.jpg",
      "similarity": 88.5, "is_match": true, "reported_at": "2026-09-10T22:01:00" }
  ],
  "path": [
    { "lat": 37.5700, "lng": 126.9820, "time": "2026-09-10T22:01:00" },
    { "lat": 37.5720, "lng": 126.9850, "time": "2026-09-10T22:20:00" }
  ]
}
```

> `path`는 **시간순 정렬**되어 있어, 그대로 지도 폴리라인으로 연결하면 이동 경로가 됩니다.

### 4) 실종자 목록

`GET /missing`

```json
{ "count": 2, "missing": [ { "id": "...", "name": "...", "description": "...",
  "last_lat": 37.5665, "last_lng": 126.9780, "photo": "...", "status": "실종중",
  "registered_at": "..." } ] }
```

### 5) 사진 가져오기

`GET /uploads/<filename>` → 이미지 파일. `<img src="{BASE}/uploads/report_x.jpg">`로 표시.

---

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
