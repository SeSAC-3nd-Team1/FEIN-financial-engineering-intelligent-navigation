
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { X } from "lucide-react";
import Header from "../components/Header";
import { TERMS } from "../data/terms";
import {
  getStockChartApi,
  getStockEvaluationApi,
  getStockPriceApi,
  getStockSummaryApi,
  type PriceResponse,
  type StockChartPeriod,
  type StockChartResponse,
  type StockEvaluationResponse,
  type StockSummaryResponse,
} from "../lib/backendApi";
import { won } from "../lib/validation";
import {
  calculatePeriodChange,
  formatMarketCap,
  formatMetric,
  isChartUnavailable,
  numeric,
  signed,
  toChartPoints,
} from "../lib/stockDetailModel";
import { useAuthStore } from "../store/authStore";
import { useTradingStore } from "../store/tradingStore";
import type { Screen, TermKey } from "../types";

interface Props {
  stockCode: string;
  userName: string;
  onNavigate: (s: Screen) => void;
  onBack: () => void;
}

type ChartMode = "simple" | "detail";
type AiMode = "bar" | "radar";

const TIMEFRAMES: { label: string; period: StockChartPeriod }[] = [
  { label: "1일", period: "1D" },
  { label: "1주", period: "1W" },
  { label: "3개월", period: "3M" },
  { label: "6개월", period: "6M" },
  { label: "1년", period: "1Y" },
  { label: "5년", period: "5Y" },
];

export default function StockDetail({
  stockCode,
  userName,
  onNavigate,
  onBack,
}: Props) {
  const token = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const portfolio = useTradingStore((state) => state.portfolio);
  const account = useTradingStore((state) => state.account);
  const [chartMode, setChartMode] = useState<ChartMode>("simple");
  const [aiMode, setAiMode] = useState<AiMode>("bar");
  const [tfIndex, setTfIndex] = useState(2);
  const [activeTooltip, setActiveTooltip] = useState<TermKey | null>(null);
  const [summary, setSummary] = useState<StockSummaryResponse | null>(null);
  const [quote, setQuote] = useState<PriceResponse | null>(null);
  const [chart, setChart] = useState<StockChartResponse | null>(null);
  const [summaryError, setSummaryError] = useState(false);
  const [quoteError, setQuoteError] = useState(false);
  const [chartError, setChartError] = useState(false);
    const [evaluation, setEvaluation] = useState<StockEvaluationResponse | null>(
    null,
  );
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [evaluationError, setEvaluationError] = useState(false);
  const [evaluationRetry, setEvaluationRetry] = useState(0);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setQuote(null);
    setQuoteError(false);
    void getStockPriceApi(stockCode, token)
      .then((response) => {
        if (active) setQuote(response);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setQuote(null);
        setQuoteError(true);
        if ((error as { status?: number }).status === 401) void logout();
      });
    return () => {
      active = false;
    };
  }, [logout, stockCode, token]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setSummary(null);
    setSummaryError(false);
    void getStockSummaryApi(stockCode, token)
      .then((response) => {
        if (active) setSummary(response);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSummary(null);
        setSummaryError(true);
        if ((error as { status?: number }).status === 401) void logout();
      });
    return () => {
      active = false;
    };
  }, [logout, stockCode, token]);

  const period = TIMEFRAMES[tfIndex].period;
  useEffect(() => {
    if (!token) return;
    let active = true;
    setChart(null);
    setChartError(false);
    void getStockChartApi(stockCode, period, token)
      .then((response) => {
        if (active) setChart(response);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setChart(null);
        setChartError(true);
        if ((error as { status?: number }).status === 401) void logout();
      });
    return () => {
      active = false;
    };
  }, [logout, period, stockCode, token]);

  useEffect(() => {
        if (!token || !account) {
      setEvaluation(null);
      setEvaluationLoading(false);
      setEvaluationError(false);
      return;
    }
        let active = true;
    setEvaluation(null);
    setEvaluationLoading(true);
    setEvaluationError(false);
    void getStockEvaluationApi(account.id, stockCode, token)
      .then((response) => {
                if (active) {
          setEvaluation(response);
          setEvaluationLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (!active) return;
        setEvaluation(null);
        setEvaluationLoading(false);
        setEvaluationError(true);
        if ((error as { status?: number }).status === 401) void logout();
      });
    return () => {
      active = false;
    };
  }, [account, evaluationRetry, logout, stockCode, token]);

  const position = portfolio?.positions.find(
    (item) => item.stock_code === stockCode,
    );

  const portfolioWeight =
    position && portfolio && Number(portfolio.total_assets) > 0
      ? (Number(position.evaluation_amount) / Number(portfolio.total_assets)) *
        100
      : null;
  const portfolioAmount = position ? Number(position.evaluation_amount) : null;
  const currentPrice = numeric(quote?.price) ?? null;
  const changeRate =
    numeric(quote?.change_rate) ?? null;
  const changeAmount =
    numeric(quote?.change_amount) ??
    (currentPrice != null && changeRate != null
      ? (currentPrice * changeRate) / 100
      : null);
  const priceData = useMemo(() => toChartPoints(chart), [chart]);
  const prices = priceData.map((item) => item.price);
  const high = prices.length ? Math.max(...prices) : null;
  const low = prices.length ? Math.min(...prices) : null;
  const periodChange = calculatePeriodChange(priceData);
  const metrics: { label: string; value: string; key: TermKey | null }[] = [
    {
      label: "시가 총액",
      value:
                summary?.market_cap == null
          ? "-"
          : formatMarketCap(summary.market_cap),
      key: null,
    },
    {
      label: "배당 수익률",
      value:
        summary?.dividend_yield == null
          ? "-"
          : formatMetric(summary.dividend_yield, "%"),
      key: "div",
    },
    {
      label: "PBR",
      value:
                summary?.pbr == null
          ? "-"
          : formatMetric(summary.pbr, "배"),
      key: "pbr",
    },
    {
      label: "PER",
      value:
                summary?.per == null
          ? "-"
          : formatMetric(summary.per, "배"),
      key: "per",
    },
    {
      label: "ROE",
      value:
                summary?.roe == null
          ? "-"
          : formatMetric(summary.roe, "%"),
      key: "roe",
    },
  ];
    const term = activeTooltip ? TERMS[activeTooltip] : null;
  const timeframe = TIMEFRAMES[tfIndex];
  const evaluationDisplay = evaluation;
  const availableAxes = (evaluationDisplay?.axes ?? []).filter(
    (axis) => axis.score != null,
  );

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-8">
          <button
            onClick={onBack}
            className="self-start text-[15px] text-muted"
          >
            ← 보유 종목으로 돌아가기
          </button>

          <section className="flex items-end justify-between gap-8">
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <h1 className="text-[40px] font-bold tracking-[-0.035em]">
                  {summary?.stock_name ?? stockCode}
                </h1>
                <span className="text-[17px] text-subtle">{stockCode}</span>
                <span className="rounded-full bg-[#F1F3EE] px-3 py-1.5 text-sm font-semibold text-muted">
                  {summary?.sector ?? "-"}
                </span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-[44px] font-bold tracking-[-0.035em]">
                  {currentPrice == null ? "-" : won(currentPrice)}
                </span>
                <span
                  className={`text-xl font-bold ${changeRate != null && changeRate > 0 ? "text-up" : changeRate != null && changeRate < 0 ? "text-down" : "text-subtle"}`}
                >
                  {changeAmount == null ? "-" : `${signed(changeAmount, 0)}원`}{" "}
                  ({signed(changeRate)}%)
                </span>
              </div>
                            {quoteError && (
                <span className="text-[15px] text-down">
                  시세를 불러올 수 없습니다.
                </span>
              )}
                            {summaryError && (
                <span className="text-[15px] text-down">
                  종목 정보를 불러올 수 없습니다.
                </span>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className="text-[15px] text-muted">내 포트폴리오 비중</span>
              <span className="text-[26px] font-bold tracking-[-0.025em]">
                {portfolioWeight == null
                  ? "-"
                  : `${portfolioWeight.toFixed(1)}%`}
              </span>
              <span className="text-base text-muted">
                {portfolioAmount == null ? "-" : won(portfolioAmount)}
              </span>
            </div>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between gap-6">
              <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
                <Toggle
                  active={chartMode === "simple"}
                  onClick={() => setChartMode("simple")}
                >
                  심플하게 보기
                </Toggle>
                <Toggle
                  active={chartMode === "detail"}
                  onClick={() => setChartMode("detail")}
                >
                  자세하게 보기
                </Toggle>
              </div>
              <div className="flex gap-2">
                {TIMEFRAMES.map((item, index) => (
                  <button
                    key={item.period}
                    onClick={() => setTfIndex(index)}
                    className={`rounded-full px-5 py-3 text-base font-semibold ${index === tfIndex ? "bg-lime text-navy" : "bg-[#F4F6F1] text-muted"}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-start justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">
                  {timeframe.label} 변화
                </span>
                <span
                  className={`text-[32px] font-bold tracking-[-0.03em] ${periodChange != null && periodChange > 0 ? "text-up" : periodChange != null && periodChange < 0 ? "text-down" : "text-subtle"}`}
                >
                  {signed(periodChange)}%
                </span>
              </div>
              {chartMode === "detail" && (
                <div className="flex gap-8 text-[15px] text-muted">
                  <span>
                    고가{" "}
                    <b className="text-ink">{high == null ? "-" : won(high)}</b>
                  </span>
                  <span>
                    저가{" "}
                    <b className="text-ink">{low == null ? "-" : won(low)}</b>
                  </span>
                </div>
              )}
            </div>
            <div className="h-[300px] w-full">
              {isChartUnavailable(chartError, priceData) ? (
                <div className="flex h-full items-center justify-center text-[17px] text-muted">
                  차트 데이터를 불러올 수 없습니다.
                </div>
              ) : (
                <ResponsiveContainer>
                  <LineChart
                    data={priceData}
                    margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                  >
                    {chartMode === "detail" && (
                      <CartesianGrid stroke="#F0F2ED" vertical={false} />
                    )}
                    {chartMode === "detail" && <XAxis dataKey="t" hide />}
                    {chartMode === "detail" && (
                      <YAxis
                        domain={["dataMin", "dataMax"]}
                        tick={{ fill: "#8A948C", fontSize: 13 }}
                        axisLine={false}
                        tickLine={false}
                        width={70}
                      />
                    )}
                    {chartMode === "detail" && (
                      <Tooltip
                        formatter={(value: number) => won(value)}
                        labelFormatter={() => ""}
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="price"
                      stroke={chartMode === "detail" ? "#18243A" : "#3E5372"}
                      strokeWidth={chartMode === "detail" ? 3 : 5}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            {chartMode === "simple" && (
              <p className="text-[17px] leading-7 text-muted">
                실제 {chart?.source ?? "시장"} 시세를 표시해요. 자세한
                고가·저가와 거래량은 “자세하게 보기”에서 볼 수 있어요.
              </p>
            )}
          </section>

          <section className="flex flex-col gap-4 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">
              어떤 회사인가요?
            </h2>
                        <p className="text-lg leading-8 text-[#3F4A43] [text-wrap:pretty]">
              {summary?.description ?? "기업 정보를 제공할 수 없습니다."}
            </p>
          </section>

          <section className="flex flex-col gap-7 rounded-card bg-surface p-12">
            <div className="flex items-center justify-between gap-6">
              <div className="flex flex-col gap-2.5">
                <span className="text-base font-semibold text-[#3F5222]">
                  ✦ AI 평가
                </span>
                <h2 className="text-[26px] font-bold tracking-[-0.025em]">
                  이 종목은 내 전략에서 이런 역할이에요
                </h2>
              </div>
              <div className="flex items-center gap-2 rounded-full bg-[#F4F6F1] p-1.5">
                <Toggle
                  active={aiMode === "bar"}
                  onClick={() => setAiMode("bar")}
                >
                  막대그래프
                </Toggle>
                <Toggle
                  active={aiMode === "radar"}
                  onClick={() => setAiMode("radar")}
                >
                  레이더그래프
                </Toggle>
              </div>
            </div>
                        {evaluationLoading ? (
              <div className="flex h-[340px] items-center justify-center text-[17px] text-muted">
                평가 데이터를 불러오는 중이에요.
              </div>
            ) : evaluationError ? (
              <div className="flex h-[340px] flex-col items-center justify-center gap-3 text-center text-[17px] text-down">
                <span>평가 데이터를 불러오지 못했습니다.</span>
                <button
                  onClick={() => setEvaluationRetry((value) => value + 1)}
                  className="rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white"
                >
                  다시 시도
                </button>
              </div>
            ) : aiMode === "bar" ? (
              <div className="flex min-h-[340px] flex-col justify-center gap-5">
                {(evaluationDisplay?.axes ?? []).map((axis) => (
                  <div
                    key={axis.key}
                    className="grid grid-cols-[120px_1fr_52px] items-center gap-5"
                  >
                    <span className="text-[16px] font-semibold text-[#3F4A43]">
                      {axis.label}
                    </span>
                    <div className="h-3 overflow-hidden rounded-full bg-[#E8ECE6]">
                      {axis.score != null && (
                        <div
                          className="h-full rounded-full bg-navy"
                          style={{ width: `${axis.score}%` }}
                        />
                      )}
                    </div>
                    <span className="text-right text-[17px] font-bold">
                      {axis.score ?? "-"}
                    </span>
                    <span className="col-span-3 text-[14px] leading-6 text-muted">
                      {axis.basis}
                    </span>
                  </div>
                ))}
                {!evaluationDisplay?.axes.length && (
                  <div className="text-center text-[17px] text-muted">
                    계산 가능한 feature 데이터를 불러오지 못했습니다.
                  </div>
                )}
              </div>
            ) : availableAxes.length >= 3 ? (
              <div className="h-[340px] w-full">
                <ResponsiveContainer>
                  <RadarChart data={availableAxes} outerRadius="72%">
                    <PolarGrid stroke="#DDE2DC" />
                    <PolarAngleAxis
                      dataKey="label"
                      tick={{ fill: "#5C665F", fontSize: 14 }}
                    />
                    <Radar
                      dataKey="score"
                      stroke="#18243A"
                      fill="#C6F04D"
                      fillOpacity={0.55}
                      strokeWidth={3}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-[340px] items-center justify-center text-[17px] text-muted">
                레이더 그래프에는 계산 가능한 축이 3개 이상 필요합니다.
              </div>
            )}
            <p className="text-[14px] text-subtle">
              {evaluation
                ? `기준일 ${evaluation.as_of ?? "-"} · 산식 ${evaluation.feature_version} · 출처 ${evaluation.sources.join(", ") || "-"}`
                : "실제 평가 데이터 없음"}
            </p>
            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-9 py-8">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">
                ✦
              </div>
              <div className="flex flex-col gap-2.5">
                <span className="text-xl font-bold tracking-[-0.02em]">
                  왜 이 비중으로 담았나요?
                </span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">
                                                      {evaluationDisplay?.role_summary ??
                    "계산 가능한 feature 또는 전략 목표 비중 데이터가 아직 없습니다."}
                </p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">
              정보 보기
            </h2>
            <div className="grid grid-cols-5 gap-4">
              {metrics.map((item) => (
                <div
                  key={item.label}
                  className="flex flex-col gap-2.5 rounded-[18px] bg-canvas px-6 py-7"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] text-muted">{item.label}</span>
                    {item.key && (
                      <button
                        aria-label={`${item.label} 설명`}
                        onClick={() =>
                          setActiveTooltip((previous) =>
                            previous === item.key ? null : item.key,
                          )
                        }
                        className={`h-5 w-5 rounded-full text-xs font-bold ${activeTooltip === item.key ? "bg-lime text-navy" : "bg-[#EDEFEA] text-muted"}`}
                      >
                        ?
                      </button>
                    )}
                  </div>
                  <span className="text-2xl font-bold tracking-[-0.025em]">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
            {term && (
              <div className="flex flex-col gap-4 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
                <div className="flex items-start justify-between gap-6">
                  <div className="flex flex-wrap items-baseline gap-2.5">
                    <span className="text-[22px] font-bold tracking-[-0.02em]">
                      {term.title}
                    </span>
                    <span className="text-[17px] text-muted">{term.ko}</span>
                  </div>
                  <button
                    aria-label="닫기"
                    onClick={() => setActiveTooltip(null)}
                    className="rounded-[9px] bg-surface p-2 text-[#3F4A43]"
                  >
                    <X size={16} />
                  </button>
                </div>
                <p className="max-w-[800px] text-lg leading-[30px] text-[#3F4A43]">
                  {term.plain}
                </p>
                <div className="flex items-center gap-3 rounded-[14px] bg-surface px-6 py-5">
                  <span className="shrink-0 text-[15px] font-semibold text-muted">
                    계산식
                  </span>
                  <span className="text-[17px] font-semibold text-ink">
                    {term.formula}
                  </span>
                </div>
              </div>
            )}
          </section>

          <p className="text-sm leading-[22px] text-subtle">
            ※ 현재가는 KIS, 일별 시세·시가총액은 KRX, 재무지표는 OpenDART
            데이터를 우선 사용합니다.
                        {quoteError ? " 일부 시세 데이터를 불러오지 못했습니다." : ""}{" "}
            투자 권유가 아닙니다.
          </p>
        </div>
      </main>
    </div>
  );
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-7 py-3.5 text-[17px] font-semibold ${active ? "bg-surface text-ink shadow-[0_2px_8px_rgba(24,36,58,0.08)]" : "text-muted"}`}
    >
      {children}
    </button>
  );
}
