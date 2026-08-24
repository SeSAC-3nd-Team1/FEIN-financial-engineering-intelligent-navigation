# KIS 실시간 시장가 및 차트 API 명세

## 1. 범위와 원칙

- Base URL: `/api/v1`
- KIS는 국내주식 현재가와 당일 분봉을 제공하는 Market Data Provider로만 사용한다.
- KIS 계좌의 주문, 잔고, 체결 API는 호출하지 않는다.
- 가상계좌, 현금, 주문, 체결, 포지션, 현금 원장, 포트폴리오는 자체 PostgreSQL에서 관리한다.
- 시장 데이터 캐시는 Redis에서 관리하며 분봉을 PostgreSQL에 저장하지 않는다.
- 모든 REST 및 WebSocket 시장가 API는 서비스 JWT 인증이 필요하다.

## 2. 현재가 조회

### `GET /market/stocks/{stock_code}/price`

현재가 소스 우선순위는 `KIS_WS` 실시간 Redis 캐시, 기존 REST Redis 캐시, KIS REST 순서다.

응답 `200`:

```json
{
  "stock_code": "005930",
  "price": "70100",
  "source": "KIS_WS",
  "as_of": "2026-08-24T10:01:23+09:00"
}
```

`source`는 `KIS_WS`, `REDIS`, `KIS` 중 하나다.

## 3. 1분봉 차트 조회

### `GET /market/stocks/{stock_code}/candles?interval=1m&limit=120`

차트 최초 렌더링에 사용할 당일 1분 OHLCV를 시간 오름차순으로 반환한다. 기존 `KisClient`의 OAuth token과 설정을 재사용하여 KIS `주식당일분봉조회`를 호출한다.

Query parameter:

| 이름 | 타입 | 기본값 | 제약 |
| --- | --- | --- | --- |
| `interval` | string | `1m` | 현재 `1m`만 지원 |
| `limit` | integer | `120` | 1~120 |

응답 `200`:

```json
{
  "stock_code": "005930",
  "interval": "1m",
  "items": [
    {
      "started_at": "2026-08-24T10:00:00+09:00",
      "open": "70000",
      "high": "70200",
      "low": "69900",
      "close": "70100",
      "volume": 1542,
      "is_closed": true
    },
    {
      "started_at": "2026-08-24T10:01:00+09:00",
      "open": "70100",
      "high": "70300",
      "low": "70000",
      "close": "70200",
      "volume": 211,
      "is_closed": false
    }
  ],
  "source": "KIS",
  "as_of": "2026-08-24T01:01:23Z"
}
```

- `started_at`은 KST(`+09:00`) 분 시작 시각이다.
- `items`는 오래된 봉부터 최신 봉 순서다.
- 현재 진행 중인 마지막 봉은 `is_closed=false`일 수 있다.
- KIS는 호출당 최대 30건을 반환하므로 Backend가 `limit`에 맞춰 최대 4회 조회하고 중복 시각을 제거한다.
- Redis key는 `market:candles:1m:{stock_code}`, 기본 TTL은 15초다.
- 캐시 응답의 `source`는 `REDIS`, KIS 직접 조회 응답은 `KIS`다.
- KIS API 특성상 당일 분봉만 제공한다. 전일 또는 기간 차트는 이 API 범위가 아니다.

차트 클라이언트는 이 REST 응답으로 초기 봉을 그리고, 아래 WebSocket `price` 이벤트의 `traded_at`을 분 단위로 내림하여 마지막 1분봉의 close/high/low/volume을 갱신할 수 있다.

## 4. 실시간 현재가 WebSocket

### `WS /market/realtime`

연결 직후 5초 안에 JWT와 구독 종목을 보낸다.

```json
{
  "action": "subscribe",
  "token": "<access-token>",
  "stock_codes": ["005930", "000660"]
}
```

구독 확인:

```json
{
  "type": "subscribed",
  "stock_codes": ["000660", "005930"],
  "connected": true
}
```

실시간 체결가:

```json
{
  "type": "price",
  "stock_code": "005930",
  "price": "70200",
  "change": "1200",
  "change_rate": "1.74",
  "trade_volume": 3,
  "accumulated_volume": 12345678,
  "traded_at": "2026-08-24T10:01:24+09:00",
  "received_at": "2026-08-24T01:01:24.031Z",
  "source": "KIS_WS",
  "is_stale": false
}
```

연결 중 추가 구독 또는 해지:

```json
{"action":"subscribe","stock_codes":["035420"]}
```

```json
{"action":"unsubscribe","stock_codes":["000660"]}
```

서버는 15초 동안 전송할 체결가가 없으면 `heartbeat`를 보낸다. JWT 만료 또는 인증 실패 시 오류 이벤트 후 WebSocket close code `4401`로 종료한다.

## 5. 실시간 상태 조회

### `GET /market/realtime/status`

응답 `200`:

```json
{
  "configured": true,
  "connected": true,
  "subscribed_symbols": 2,
  "downstream_clients": 1,
  "last_received_at": "2026-08-24T01:01:24.031Z",
  "last_error": null
}
```

## 6. 오류 계약

REST 오류 형식:

```json
{"code":"KIS_UNAVAILABLE","message":"현재 시장가격을 조회하지 못했습니다."}
```

| HTTP status | code | 의미 |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 서비스 JWT 누락 또는 오류 |
| 404 | `STOCK_NOT_FOUND` | KIS에서 종목을 조회할 수 없음 |
| 422 | FastAPI validation error | 종목코드, interval, limit 형식 오류 |
| 503 | `KIS_NOT_CONFIGURED` | KIS credential 미설정 |
| 503 | `KIS_RATE_LIMIT` | KIS 조회 한도 초과 |
| 503 | `KIS_UNAVAILABLE` | KIS 통신 또는 응답 형식 오류 |

WebSocket 오류 이벤트:

```json
{"type":"error","code":"INVALID_SUBSCRIPTION","message":"인증 토큰과 유효한 구독 종목이 필요합니다."}
```

## 7. 환경변수

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `KIS_APP_KEY` | 없음 | KIS App Key |
| `KIS_APP_SECRET` | 없음 | KIS App Secret |
| `KIS_BASE_URL` | `https://openapi.koreainvestment.com:9443` | KIS REST URL |
| `KIS_WEBSOCKET_URL` | `ws://ops.koreainvestment.com:21000` | KIS WebSocket URL |
| `PRICE_CACHE_TTL_SECONDS` | `5` | 현재가 REST cache TTL |
| `MINUTE_CANDLE_CACHE_TTL_SECONDS` | `15` | 당일 1분봉 cache TTL |
| `REALTIME_PRICE_CACHE_TTL_SECONDS` | `30` | 실시간 현재가 Redis TTL |
| `REALTIME_PRICE_STALE_SECONDS` | `10` | 실시간 현재가 허용 age |
| `KIS_REALTIME_MAX_SYMBOLS_PER_CLIENT` | `20` | WebSocket client당 최대 종목 수 |

## 8. 데이터 저장 경계

```text
KIS REST ── 현재가/당일 1분봉 ──> Backend ──> Redis 단기 캐시
KIS WS   ── 실시간 체결가 ─────> Backend ──> Redis 최신값 + WebSocket fan-out

Frontend/API ── 가상 주문 ─────> PostgreSQL
                                ├─ virtual_accounts / cash_balances
                                ├─ orders / executions / positions
                                ├─ cash_ledger
                                └─ portfolio evaluation
```

시장가 조회 실패 시 실제 KIS 주문으로 우회하지 않으며, PostgreSQL 가상거래 원장도 시장 데이터 저장소로 사용하지 않는다.
