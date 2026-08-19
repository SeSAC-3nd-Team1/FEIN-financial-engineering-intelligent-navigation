# KIS 실시간 투자 대시보드 PoC

React + Vite 프론트엔드와 FastAPI 백엔드에서 한국투자증권 Open API 연동 가능성을 빠르게 검증하기 위한 브랜치입니다.

## 검증 범위

- REST 분봉 조회 후 SVG 캔들차트 표시
- KIS WebSocket 실시간 체결가를 현재 1분봉에 반영
- 국내주식 현금 매수/매도 주문
- 주식잔고조회 기반 총 평가금액, 예수금, 평가손익, 보유 종목 표시
- KIS 키가 없는 개발환경에서는 Mock 데이터를 명확히 표시한 상태로 UI 검증

## 안전 기본값

- `KIS_MODE=paper`: 기본은 모의투자입니다.
- `KIS_ENABLE_LIVE_TRADING=false`: 실전 계좌 주문은 명시적으로 활성화하기 전까지 서버에서 거부합니다.
- App Key, App Secret, 계좌번호는 `.env`에만 두고 Git에 커밋하지 않습니다.

## 실행

```bash
cp .env.example .env
```

`.env`에 한국투자증권 모의투자 정보를 입력합니다.

```env
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=12345678
KIS_ACCOUNT_PRODUCT_CODE=01
KIS_MODE=paper
KIS_USE_MOCK_FALLBACK=false
KIS_ENABLE_LIVE_TRADING=false
```

그 다음 기존 개발환경과 동일하게 실행합니다.

```bash
docker compose up -d --build
```

브라우저에서 `http://localhost:5173`으로 접속합니다.

## 데이터 흐름

```text
KIS REST (분봉/잔고/주문) ─┐
                           ├─ FastAPI ─ REST/WebSocket ─ React + Vite Dashboard
KIS WebSocket (실시간체결) ─┘
```

프론트엔드는 App Key/Secret을 보유하지 않습니다. 모든 KIS 인증과 주문 요청은 FastAPI가 수행합니다.

## API

- `GET /kis/status`
- `GET /kis/price/{symbol}`
- `GET /kis/chart/{symbol}`
- `GET /kis/account`
- `POST /kis/order`
- `WS /ws/kis/{symbol}`

## 확인할 것

1. 대시보드 상단이 `KIS PAPER`로 표시되는지 확인합니다.
2. 장중 삼성전자 등의 가격이 WebSocket으로 계속 갱신되는지 확인합니다.
3. 모의투자 계좌 잔고가 화면에 표시되는지 확인합니다.
4. 1주 시장가 매수/매도 후 주문번호가 반환되고 잔고 새로고침에 반영되는지 확인합니다.
5. 장 마감 후에는 실시간 체결이 발생하지 않을 수 있으므로 REST 분봉과 계좌/주문 기능을 별도로 확인합니다.

실전 계좌 검증이 필요한 경우에만 `KIS_MODE=real`과 `KIS_ENABLE_LIVE_TRADING=true`를 함께 설정합니다. 실전 주문은 실제 주문이므로 PoC 단계에서는 권장하지 않습니다.
