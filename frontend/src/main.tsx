import { StrictMode, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Candle = { time: string; open: number; high: number; low: number; close: number; volume: number };
type Tick = { symbol: string; time: string; price: number; change: number; changeRate: number; volume: number; source: string };
type Holding = { symbol: string; name: string; quantity: number; availableQuantity: number; avgPrice: number; currentPrice: number; evaluationAmount: number; profitLoss: number; profitLossRate: number };
type Account = { summary: { cash: number; stockEvaluation: number; totalEvaluation: number; profitLoss: number; profitLossRate: number }; holdings: Holding[]; source: string };
type Status = { configured: boolean; accountConfigured: boolean; mode: "paper" | "real"; source: "mock" | "kis"; liveTradingEnabled: boolean; message: string };

const STOCKS = [
  { symbol: "005930", name: "삼성전자" },
  { symbol: "000660", name: "SK하이닉스" },
  { symbol: "035420", name: "NAVER" },
];
const won = new Intl.NumberFormat("ko-KR");
const pct = (value: number) => `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const money = (value: number) => `${won.format(Math.round(value))}원`;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function CandleChart({ candles }: { candles: Candle[] }) {
  const width = 920, height = 300, padX = 52, padY = 22;
  const data = candles.slice(-70);
  const min = data.length ? Math.min(...data.map((c) => c.low)) : 0;
  const max = data.length ? Math.max(...data.map((c) => c.high)) : 1;
  const range = Math.max(1, max - min);
  const plotW = width - padX * 2, plotH = height - padY * 2;
  const y = (value: number) => padY + ((max - value) / range) * plotH;
  const step = data.length ? plotW / data.length : plotW;
  const candleW = Math.max(2, Math.min(8, step * 0.62));
  if (!data.length) return <div className="chart-empty">차트 데이터를 불러오는 중입니다.</div>;
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="실시간 주가 캔들 차트">
      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
        const yy = padY + ratio * plotH; const value = max - ratio * range;
        return <g key={ratio}><line x1={padX} x2={width - padX} y1={yy} y2={yy} className="grid-line"/><text x={width - padX + 6} y={yy + 4} className="axis-text">{won.format(Math.round(value))}</text></g>;
      })}
      {data.map((c, i) => {
        const x = padX + i * step + step / 2; const up = c.close >= c.open;
        const bodyTop = y(Math.max(c.open, c.close)); const bodyBottom = y(Math.min(c.open, c.close));
        return <g key={`${c.time}-${i}`} className={up ? "candle-up" : "candle-down"}>
          <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} className="wick"/>
          <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={Math.max(1, bodyBottom - bodyTop)} rx="1"/>
        </g>;
      })}
      <text x={padX} y={height - 3} className="axis-text">{data[0]?.time.slice(0, 4)}</text>
      <text x={width - padX - 30} y={height - 3} className="axis-text">{data.at(-1)?.time.slice(0, 4)}</text>
    </svg>
  );
}

function App() {
  const [symbol, setSymbol] = useState("005930");
  const [status, setStatus] = useState<Status | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [tick, setTick] = useState<Tick | null>(null);
  const [socketState, setSocketState] = useState("연결 중");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState(1);
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState(0);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const stock = useMemo(() => STOCKS.find((item) => item.symbol === symbol) ?? { symbol, name: symbol }, [symbol]);

  const refreshAccount = () => api<Account>("/kis/account").then(setAccount).catch((error) => setNotice(error.message));

  useEffect(() => { api<Status>("/kis/status").then(setStatus).catch((error) => setNotice(error.message)); refreshAccount(); }, []);

  useEffect(() => {
    setSocketState("연결 중"); setTick(null);
    api<Candle[]>(`/kis/chart/${symbol}`).then(setCandles).catch((error) => setNotice(error.message));
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/api/ws/kis/${symbol}`);
    wsRef.current = socket;
    socket.onopen = () => setSocketState("실시간 연결");
    socket.onerror = () => setSocketState("연결 오류");
    socket.onclose = () => setSocketState("연결 종료");
    socket.onmessage = (event) => {
      const next = JSON.parse(event.data) as Tick & { type?: string; message?: string };
      if (next.type === "error") { setNotice(next.message ?? "WebSocket 오류"); return; }
      setTick(next);
      setCandles((prev) => {
        const minute = next.time.slice(0, 4); const rows = [...prev]; const last = rows.at(-1);
        if (last && last.time.slice(0, 4) === minute) {
          rows[rows.length - 1] = { ...last, high: Math.max(last.high, next.price), low: Math.min(last.low, next.price), close: next.price, volume: last.volume + (next.volume || 0) };
        } else {
          rows.push({ time: next.time, open: next.price, high: next.price, low: next.price, close: next.price, volume: next.volume || 0 });
        }
        return rows.slice(-120);
      });
    };
    return () => socket.close();
  }, [symbol]);

  useEffect(() => { if (tick?.price && orderType === "limit" && limitPrice === 0) setLimitPrice(tick.price); }, [tick?.price, orderType]);

  const submitOrder = async () => {
    setLoading(true); setNotice("");
    try {
      const result = await api<{ message: string; orderNumber: string; source: string }>("/kis/order", {
        method: "POST", body: JSON.stringify({ symbol, side, quantity, order_type: orderType, price: orderType === "limit" ? limitPrice : null }),
      });
      setNotice(`${result.message}${result.orderNumber ? ` · 주문번호 ${result.orderNumber}` : ""}`); await refreshAccount();
    } catch (error) { setNotice(error instanceof Error ? error.message : "주문 실패"); }
    finally { setLoading(false); }
  };

  const currentPrice = tick?.price ?? candles.at(-1)?.close ?? 0;
  const changeRate = tick?.changeRate ?? 0;
  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div><p className="eyebrow">FE!N · KIS Open API PoC</p><h1>실시간 투자 대시보드</h1></div>
        <div className="status-row">
          <span className={`badge ${status?.source === "kis" ? "ok" : "warn"}`}>{status?.source === "kis" ? `KIS ${status.mode.toUpperCase()}` : "MOCK DATA"}</span>
          <span className={`badge ${socketState === "실시간 연결" ? "ok" : "neutral"}`}>{socketState}</span>
        </div>
      </header>

      {status && <div className={`mode-banner ${status.source === "mock" ? "mock" : "live"}`}><strong>{status.message}</strong><span>{status.mode === "real" && !status.liveTradingEnabled ? "실전 주문 잠금 상태" : "주문 기능 활성"}</span></div>}
      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")}>닫기</button></div>}

      <section className="metrics-grid">
        <article className="metric"><span>총 평가금액</span><strong>{money(account?.summary.totalEvaluation ?? 0)}</strong><small className={(account?.summary.profitLoss ?? 0) >= 0 ? "positive" : "negative"}>{money(account?.summary.profitLoss ?? 0)} · {pct(account?.summary.profitLossRate ?? 0)}</small></article>
        <article className="metric"><span>주식 평가금액</span><strong>{money(account?.summary.stockEvaluation ?? 0)}</strong><small>보유 종목 {account?.holdings.length ?? 0}개</small></article>
        <article className="metric"><span>예수금</span><strong>{money(account?.summary.cash ?? 0)}</strong><small>주문 가능 현금 기준</small></article>
        <article className="metric"><span>현재 종목</span><strong>{money(currentPrice)}</strong><small className={changeRate >= 0 ? "positive" : "negative"}>{stock.name} · {pct(changeRate)}</small></article>
      </section>

      <section className="workspace-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <div><span className="section-label">REALTIME MARKET</span><h2>{stock.name} <small>{symbol}</small></h2></div>
            <select value={symbol} onChange={(event: ChangeEvent<HTMLSelectElement>) => setSymbol(event.target.value)}>{STOCKS.map((item) => <option value={item.symbol} key={item.symbol}>{item.name} · {item.symbol}</option>)}</select>
          </div>
          <div className="quote-line"><strong>{money(currentPrice)}</strong><span className={changeRate >= 0 ? "positive" : "negative"}>{tick ? `${tick.change >= 0 ? "+" : ""}${won.format(tick.change)} (${pct(changeRate)})` : "실시간 체결 대기"}</span></div>
          <CandleChart candles={candles}/>
          <div className="chart-foot"><span>1분봉 + WebSocket 체결 반영</span><span>최근 체결량 {won.format(tick?.volume ?? 0)}</span></div>
        </article>

        <article className="panel order-panel">
          <div className="panel-head"><div><span className="section-label">ORDER</span><h2>매수 · 매도</h2></div></div>
          <div className="segmented"><button className={side === "buy" ? "active buy" : ""} onClick={() => setSide("buy")}>매수</button><button className={side === "sell" ? "active sell" : ""} onClick={() => setSide("sell")}>매도</button></div>
          <label>종목<input value={`${stock.name} (${symbol})`} disabled/></label>
          <label>주문 수량<input type="number" min="1" value={quantity} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuantity(Math.max(1, Number(event.target.value)))}/></label>
          <label>주문 방식<select value={orderType} onChange={(event: ChangeEvent<HTMLSelectElement>) => setOrderType(event.target.value as "market" | "limit")}><option value="market">시장가</option><option value="limit">지정가</option></select></label>
          {orderType === "limit" && <label>주문 가격<input type="number" min="0" step="100" value={limitPrice} onChange={(event: ChangeEvent<HTMLInputElement>) => setLimitPrice(Number(event.target.value))}/></label>}
          <div className="order-estimate"><span>예상 주문금액</span><strong>{money((orderType === "market" ? currentPrice : limitPrice) * quantity)}</strong></div>
          <button className={`order-button ${side}`} disabled={loading || currentPrice === 0} onClick={submitOrder}>{loading ? "주문 요청 중..." : `${side === "buy" ? "매수" : "매도"} 주문`}</button>
          <p className="helper">기본 환경은 모의투자입니다. 실전 주문은 서버의 보호 플래그를 켜기 전까지 차단됩니다.</p>
        </article>
      </section>

      <section className="panel holdings-panel">
        <div className="panel-head"><div><span className="section-label">PORTFOLIO</span><h2>현재 투자 운용 현황</h2></div><button className="ghost" onClick={refreshAccount}>새로고침</button></div>
        <div className="table-wrap"><table><thead><tr><th>종목</th><th>보유</th><th>평균단가</th><th>현재가</th><th>평가금액</th><th>평가손익</th><th>수익률</th></tr></thead><tbody>
          {(account?.holdings ?? []).map((item) => <tr key={item.symbol}><td><strong>{item.name}</strong><small>{item.symbol}</small></td><td>{won.format(item.quantity)}주</td><td>{money(item.avgPrice)}</td><td>{money(item.currentPrice)}</td><td>{money(item.evaluationAmount)}</td><td className={item.profitLoss >= 0 ? "positive" : "negative"}>{money(item.profitLoss)}</td><td className={item.profitLossRate >= 0 ? "positive" : "negative"}>{pct(item.profitLossRate)}</td></tr>)}
          {!account?.holdings.length && <tr><td colSpan={7} className="empty-row">보유 종목이 없습니다.</td></tr>}
        </tbody></table></div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
