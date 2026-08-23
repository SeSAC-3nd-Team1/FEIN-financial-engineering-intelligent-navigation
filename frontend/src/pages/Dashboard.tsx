import { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import Header from '../components/Header';
import { ALL_HOLDINGS as MOCK_HOLDINGS, HOLD_TOTAL as MOCK_HOLD_TOTAL } from '../data/holdings';
import { useTradingData } from '../hooks/useTradingData';
import { won } from '../lib/validation';
import { useTradingStore } from '../store/tradingStore';
import type { Screen } from '../types';

interface Props {
  userName: string;
  strategyName: string;
  onNavigate: (s: Screen) => void;
  onOpenHoldings: () => void;
  onChangeStrategy: () => void;
}

/** 05 포트폴리오 대시보드 — 스토리 → 리밸런싱 제안 → 판단 성적표 → 전략 */
export default function Dashboard({ userName, strategyName, onNavigate, onOpenHoldings, onChangeStrategy }: Props) {
  useTradingData();
  const portfolio = useTradingStore((state) => state.portfolio);
  const accountMissing = useTradingStore((state) => state.accountMissing);
  const isLoading = useTradingStore((state) => state.isLoading);
  const isRefreshing = useTradingStore((state) => state.isRefreshing);
  const error = useTradingStore((state) => state.error);
  const [sheetOpen, setSheetOpen] = useState(false); // 리밸런싱 상세 시트

  /** 오늘 손익 = 평가금액 × 등락률. 스토리와 요약이 같은 계산을 공유한다 */
  const { todayTotal, top } = useMemo(() => {
    const gains = MOCK_HOLDINGS.map((h) => ({ name: h.name, gain: (MOCK_HOLD_TOTAL * h.pct) / 100 * (h.chg / 100) }));
    const total = gains.reduce((a, g) => a + g.gain, 0);
    return { todayTotal: total, top: [...gains].sort((a, b) => b.gain - a.gain)[0] };
  }, []);

  if (!portfolio) {
    return (
      <DashboardState
        userName={userName}
        onNavigate={onNavigate}
        title={isLoading ? '가상계좌를 불러오고 있어요…' : accountMissing ? '아직 가상계좌가 없어요' : '포트폴리오를 불러오지 못했어요'}
        message={isLoading ? '계좌와 보유종목을 확인하고 있습니다.' : accountMissing ? '전략을 선택하고 가상투자를 시작해주세요.' : error?.message ?? '잠시 후 다시 시도해주세요.'}
      />
    );
  }

  const profit = Number(portfolio.unrealized_profit) + Number(portfolio.realized_profit);

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-16">
          <section className="flex flex-col gap-5">
            <span className="text-base font-semibold text-muted">오늘의 포트폴리오</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
              {userName}님의 투자는<br />오늘도 전략대로 움직이고 있어요.
            </h1>
            <div className="flex items-baseline gap-4">
              <span className="text-[32px] font-bold tracking-[-0.03em]">{won(Number(portfolio.total_assets))}</span>
              <span className={`text-[19px] font-semibold ${profit >= 0 ? 'text-up' : 'text-down'}`}>
                평가·실현 {profit >= 0 ? '+' : ''}{Math.round(profit).toLocaleString('ko-KR')}원 ({Number(portfolio.return_rate).toFixed(2)}%)
              </span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <Fact label="현금잔액" value={won(Number(portfolio.cash_balance))} />
              <Fact label="총 매입금액" value={won(Number(portfolio.total_purchase_amount))} />
              <Fact label="총 평가금액" value={won(Number(portfolio.total_evaluation_amount))} />
              <Fact label="실현손익" value={won(Number(portfolio.realized_profit))} warn={Number(portfolio.realized_profit) < 0} />
            </div>
            {isRefreshing && <span className="text-sm text-subtle">최신 가격으로 갱신 중…</span>}
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-2 rounded-full bg-[#EAF7EF] px-3.5 py-2 text-[15px] font-semibold text-[#2E9B65]">
                ● 선택 전략
              </span>
              <span className="text-[17px] text-muted">현재 가상계좌에는 {strategyName}이 선택되어 있어요.</span>
            </div>
          </section>

          {/* 포트폴리오 스토리 — 의미 → 숫자 순서 */}
          <section className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">오늘 내 투자에는 무슨 일이 있었나요?</h2>
              <span className="rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">AI 설명 예시 · MOCK</span>
            </div>
            <div className="flex flex-col gap-4">
              <Story title={`${top.name}가 오늘 수익을 가장 많이 만들었어요`}>
                <div className="flex items-baseline gap-4">
                  <span className="text-2xl font-bold text-up">+{Math.round(top.gain).toLocaleString('ko-KR')}원</span>
                  <span className="text-[17px] text-muted">오늘 전체 수익의 {Math.round((top.gain / todayTotal) * 100)}%</span>
                </div>
                <span className="pt-1 text-base font-semibold text-navy">왜 올랐나요? →</span>
              </Story>

              <Story title="많이 오른 만큼 비중도 목표보다 커졌어요">
                <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                  <span>목표 14%</span><span className="text-[#A6AFA7]">→</span><span className="font-bold">현재 16.2%</span>
                </div>
                <span className="text-[17px] leading-7 text-muted">어떻게 하면 좋을지 아래에서 AI 제안을 확인해보세요.</span>
              </Story>

              <Story title="KT&G는 포트폴리오의 흔들림을 줄여줬어요">
                <span className="text-[17px] leading-7 text-muted">오늘 시장보다 변동성이 낮았어요.</span>
              </Story>
            </div>
          </section>

          {/* AI 리밸런싱 제안 — 명령이 아니라 제안 */}
          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex gap-5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
              <div className="flex flex-1 flex-col gap-4">
                <div className="flex items-center gap-3">
                  <span className="text-[26px] font-bold tracking-[-0.025em]">AI가 확인할 게 하나 있어요</span>
                  <span className="rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">MOCK</span>
                </div>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">
                  SK하이닉스 비중이 전략 목표보다 높아졌어요.
                </p>
                <div className="flex gap-10 rounded-[18px] bg-canvas px-8 py-6">
                  <Fact label="목표" value="14%" />
                  <Fact label="현재" value="18.7%" warn />
                  <Fact label="추천" value="약 47,000원 줄이기" />
                </div>
                <div className="flex items-center gap-3 pt-1">
                  <button onClick={() => setSheetOpen(true)} className="rounded-field bg-lime px-8 py-4 text-[17px] font-bold text-navy">
                    제안 확인하기
                  </button>
                </div>
              </div>
            </div>
          </section>

          {/* 포트폴리오 시각화 진입 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-2xl font-bold tracking-[-0.025em]">내 돈은 지금 이렇게 나뉘어 있어요</span>
              <span className="text-[17px] leading-7 text-muted">실제 보유 {portfolio.positions.length}개 종목의 평가금액과 수익률을 확인할 수 있어요.</span>
            </div>
            <button onClick={onOpenHoldings} className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]">
              실제 보유종목 보기 →
            </button>
          </section>

          {/* 판단 성적표 — 평가가 아니라 기록 */}
          <section className="flex flex-col gap-6">
            <div className="flex flex-col gap-3.5">
              <div className="flex items-center gap-3">
                <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">내 투자 판단은 어땠을까요?</h2>
                <span className="rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">MOCK</span>
              </div>
              <p className="text-lg leading-[30px] text-muted">
                AI 제안을 따랐을 때와 내가 선택한 결과를 함께 돌아볼 수 있어요.
              </p>
            </div>
            <div className="flex flex-col gap-5 rounded-card bg-surface p-12">
              <div className="flex flex-col gap-3">
                <span className="text-[15px] text-muted">지난 리밸런싱</span>
                <div className="flex items-center gap-3.5 text-[19px] text-[#3F4A43]">
                  <span>AI 제안 <b>삼성전자 비중 3% 줄이기</b></span>
                  <span className="text-[#A6AFA7]">·</span>
                  <span>내 선택 <b>하지 않음</b></span>
                </div>
                <span className="text-[17px] text-muted">그 이후 삼성전자 -6.4%</span>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                  <span className="text-[15px] text-muted">AI 제안을 따랐다면</span>
                  <span className="text-[26px] font-bold tracking-[-0.03em] text-up">현재 자산 +12,400원</span>
                </div>
                <div className="flex flex-col gap-2 rounded-[18px] bg-canvas px-8 py-7">
                  <span className="text-[15px] text-muted">실제 내 선택</span>
                  <span className="text-[26px] font-bold tracking-[-0.03em] text-down">현재 자산 -3,800원</span>
                </div>
              </div>
              <p className="text-[17px] leading-7 text-muted">
                이번에는 AI 제안을 따랐을 때 변동성이 조금 더 낮았어요.
              </p>
              <span className="text-base font-semibold text-navy">지난 판단 돌아보기 →</span>
            </div>
          </section>

          {/* 전략 변경 — Primary 로 강조하지 않는다 */}
          <section className="flex items-center justify-between gap-8 rounded-card bg-surface px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] text-muted">현재 전략</span>
              <span className="text-2xl font-bold tracking-[-0.025em]">{strategyName}</span>
              <span className="text-base text-muted">나와 92% 잘 맞아요</span>
            </div>
            <button onClick={onChangeStrategy} className="shrink-0 rounded-field bg-[#F4F6F1] px-7 py-4 text-[17px] font-semibold text-[#3F4A43]">
              전략 변경하기
            </button>
          </section>
        </div>
      </main>

      {/* 05_Rebalancing_Detail — Before → After */}
      {sheetOpen && (
        <div className="fixed inset-0 z-[700] flex items-center justify-center bg-navy/40 p-8" onClick={() => setSheetOpen(false)}>
          <div className="flex w-[720px] flex-col gap-7 rounded-card bg-surface p-12" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-6">
              <h2 className="text-[28px] font-bold leading-10 tracking-[-0.03em]">왜 지금 비중을 조정하라고 하나요?</h2>
              <button aria-label="닫기" onClick={() => setSheetOpen(false)} className="rounded-[9px] bg-canvas p-2 text-muted">
                <X size={18} />
              </button>
            </div>
            <p className="text-lg leading-[30px] text-[#3F4A43]">
              SK하이닉스가 최근 상승하면서 처음 정했던 14%보다 비중이 커졌어요.
            </p>
            <div className="flex items-center gap-6 rounded-[18px] bg-canvas px-8 py-7">
              <div className="flex flex-1 flex-col gap-2">
                <span className="text-[15px] text-muted">현재</span>
                <span className="text-[28px] font-bold tracking-[-0.03em] text-warn">18.7%</span>
                <div className="h-2.5 rounded-full bg-[#E5E9E3]"><div className="h-2.5 rounded-full bg-warn" style={{ width: '18.7%' }} /></div>
              </div>
              <span className="text-2xl text-[#A6AFA7]">→</span>
              <div className="flex flex-1 flex-col gap-2">
                <span className="text-[15px] text-muted">조정 후</span>
                <span className="text-[28px] font-bold tracking-[-0.03em]">14.2%</span>
                <div className="h-2.5 rounded-full bg-[#E5E9E3]"><div className="h-2.5 rounded-full bg-navy" style={{ width: '14.2%' }} /></div>
              </div>
            </div>
            <div className="flex flex-col gap-2.5 rounded-[18px] bg-[#F8FCEE] px-8 py-7">
              <span className="text-lg font-bold tracking-[-0.02em]">조정하지 않으면?</span>
              <p className="text-[17px] leading-7 text-[#3F4A43]">
                특정 종목의 영향이 커져 저변동성 전략보다 포트폴리오가 더 많이 흔들릴 수 있어요.
              </p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setSheetOpen(false)} className="flex-1 rounded-field bg-lime py-5 text-lg font-bold text-navy">
                47,000원 조정하기
              </button>
              <button onClick={() => setSheetOpen(false)} className="rounded-field bg-[#F4F6F1] px-8 py-5 text-[17px] font-semibold text-[#3F4A43]">
                이번에는 하지 않을게요
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardState({
  userName, onNavigate, title, message,
}: { userName: string; onNavigate: (s: Screen) => void; title: string; message: string }) {
  return (
    <div className="min-h-screen bg-canvas">
      <Header active="portfolio" userName={userName} onNavigate={onNavigate} />
      <main className="flex justify-center px-16 pt-20">
        <section className="flex w-[720px] flex-col items-center gap-4 rounded-card bg-surface p-14 text-center">
          <h1 className="text-[30px] font-bold">{title}</h1>
          <p role="status" className="text-lg text-muted">{message}</p>
          <button onClick={() => onNavigate('strategy')} className="mt-3 rounded-field bg-lime px-7 py-4 font-bold text-navy">전략 둘러보기</button>
        </section>
      </main>
    </div>
  );
}

function Story({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3.5 rounded-card bg-surface px-11 py-10">
      <span className="text-[26px] font-bold leading-[38px] tracking-[-0.025em]">{title}</span>
      {children}
    </div>
  );
}

function Fact({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[15px] text-muted">{label}</span>
      <span className={`text-xl font-bold ${warn ? 'text-warn' : ''}`}>{value}</span>
    </div>
  );
}
