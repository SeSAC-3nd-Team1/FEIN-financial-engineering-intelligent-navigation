import { useMemo, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import { ChevronRight } from 'lucide-react';
import Header from '../components/Header';
import { ALL_HOLDINGS as MOCK_TARGET_HOLDINGS } from '../data/holdings';
import { won } from '../lib/validation';
import type { Holding, Screen } from '../types';

interface Props {
  userName: string;
  /** RiskResult/StrategyDetail 에서 선택한 전략의 표시 이름 (예: "저변동성 전략") */
  strategyName: string;
  onNavigate: (s: Screen) => void;
  onStart: () => Promise<void>;
  onSelectStock: (index: number) => void;
}

const PRESETS = [100_000, 500_000, 1_000_000, 5_000_000];
/** 도넛 색: Deep Navy 계열 + 중립. 선택된 조각만 라임 */
const SHADES = ['#18243A', '#2E4160', '#4A5F80', '#6C819E', '#C3CBC4'];
/** 전략 목표 비중 (target 이 있으면 그 값을 쓴다) */
const displayPct = (h: Holding) => h.target ?? h.pct;

/** row 선택 상태 — 대표 4종목/나머지 16종목은 ALL_HOLDINGS 인덱스로, 집계 행("기타 N개 종목")은 별도로 구분 */
type Selection = { kind: 'holding'; index: number } | { kind: 'other' };

export default function StartInvesting({ userName, strategyName, onNavigate, onStart, onSelectStock }: Props) {
  const [amount, setAmount] = useState(1_000_000);
  const [custom, setCustom] = useState<string | null>(null); // null = 직접 입력 꺼짐
  const [selection, setSelection] = useState<Selection>({ kind: 'holding', index: 0 });
  const [restExpanded, setRestExpanded] = useState(false);
  const [mode, setMode] = useState<'manual' | 'auto'>('manual');
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const topHoldings = MOCK_TARGET_HOLDINGS.slice(0, 4);
  const restHoldings = MOCK_TARGET_HOLDINGS.slice(4);

  /** 04는 전략 목표 비중으로 새로 담는다 — 도넛 차트는 대표 4종목 + 기타 합계, 5조각 그대로 유지 */
  const slices = useMemo(() => {
    const top = topHoldings.map((h) => ({ name: h.name, pct: displayPct(h) }));
    const restPct = Math.round((100 - top.reduce((a, h) => a + h.pct, 0)) * 10) / 10;
    return [...top, { name: `기타 ${restHoldings.length}개 종목`, pct: restPct }];
  }, []);
  const otherLabel = slices[4];

  // 도넛은 5조각(대표4 + 기타)까지만 있으므로, 나머지 16종목 중 하나를 선택해도 "기타" 조각이 강조된다
  const donutActiveIndex = selection.kind === 'holding' && selection.index < 4 ? selection.index : 4;

  const sel = selection.kind === 'other'
    ? { name: otherLabel.name, pct: otherLabel.pct, why: '한 종목에 쏠리지 않도록 나머지를 고르게 나눠 담았어요.' }
    : { name: MOCK_TARGET_HOLDINGS[selection.index].name, pct: displayPct(MOCK_TARGET_HOLDINGS[selection.index]), why: MOCK_TARGET_HOLDINGS[selection.index].why };

  const commitCustom = () => {
    const n = parseInt(custom ?? '', 10);
    if (!n) { setCustom(String(amount)); return; }
    const clamped = Math.min(100_000_000, Math.max(100_000, n));
    setAmount(clamped);
    setCustom(String(clamped));
  };

  return (
    <div className="min-h-screen bg-canvas">
      <Header active="strategy" userName={userName} onNavigate={onNavigate} />

      <main className="flex flex-col items-center px-16 pb-24 pt-6">
        <div className="flex w-[1040px] flex-col gap-10">
          <section className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">{strategyName}으로 시작하기</span>
            <h1 className="text-[44px] font-bold leading-[62px] tracking-[-0.035em]">얼마로 시작해볼까요?</h1>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <div className="flex gap-3">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  onClick={() => { setAmount(p); setCustom(null); }}
                  className={`rounded-full px-6 py-3.5 text-base font-semibold ${
                    amount === p && custom === null ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-muted'
                  }`}
                >
                  {(p / 10000).toLocaleString('ko-KR')}만원
                </button>
              ))}
            </div>

            <div className="flex items-end justify-between gap-8">
              <div className="flex flex-col gap-2">
                <span className="text-base text-muted">선택한 투자 금액</span>
                {custom === null ? (
                  <span className="text-[44px] font-bold tracking-[-0.035em]">{won(amount)}</span>
                ) : (
                  <>
                    {/* 직접 입력: 숫자만 받고 blur/Enter 에서 10만~1억으로 보정 */}
                    <div className="flex items-center gap-3">
                      <input
                        value={custom}
                        inputMode="numeric"
                        onChange={(e) => setCustom(e.target.value.replace(/[^\d]/g, '').slice(0, 9))}
                        onBlur={commitCustom}
                        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
                        placeholder="1000000"
                        className="w-[300px] border-b-2 border-lime bg-transparent px-4 py-3.5 text-[40px] font-bold tracking-[-0.035em] outline-none"
                      />
                      <span className="text-[32px] font-bold text-muted">원</span>
                    </div>
                    <span className="text-[15px] text-subtle">10만원 ~ 1억원 사이로 입력해주세요</span>
                  </>
                )}
              </div>
              <div className="flex flex-col items-end gap-2">
                <button
                  onClick={() => setCustom(custom === null ? String(amount) : null)}
                  className="text-base font-semibold text-navy underline"
                >
                  {custom === null ? '직접 입력' : '금액 선택으로 돌아가기'}
                </button>
                <span className="text-[15px] text-subtle">시작 후에도 언제든 조절할 수 있어요</span>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-8 rounded-card bg-surface p-12">
            <span className="self-start rounded-full bg-[#F4F6F1] px-3 py-1.5 text-xs font-bold text-muted">전략 배분 예시 · MOCK</span>
            <h2 className="text-[32px] font-bold leading-[46px] tracking-[-0.03em]">
              {(amount / 10000).toLocaleString('ko-KR')}만원을 투자하면 이렇게 나눠 담아요
            </h2>

            <div className="flex items-center gap-14">
              <div className="relative h-[320px] w-[320px] shrink-0">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={slices}
                      dataKey="pct"
                      innerRadius="62%"
                      outerRadius="100%"
                      startAngle={90}
                      endAngle={-270}
                      paddingAngle={1.5}
                      stroke="none"
                      onClick={(_, i) => setSelection(i === 4 ? { kind: 'other' } : { kind: 'holding', index: i })}
                    >
                      {slices.map((_, i) => (
                        /* 선택된 조각만 라임 — 나머지는 네이비 계열 */
                        <Cell key={i} fill={i === donutActiveIndex ? '#C6F04D' : SHADES[i]} cursor="pointer" />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
                  <span className="text-[32px] font-bold tracking-[-0.035em]">
                    {(amount / 10000).toLocaleString('ko-KR')}만원
                  </span>
                  <span className="text-base text-muted">{MOCK_TARGET_HOLDINGS.length}개 종목</span>
                </div>
              </div>

              <div className="flex flex-1 flex-col gap-1">
                {topHoldings.map((h, i) => (
                  <StockRow
                    key={h.name}
                    name={h.name}
                    pct={displayPct(h)}
                    amountWon={won((amount * displayPct(h)) / 100)}
                    dotColor={i === donutActiveIndex ? '#C6F04D' : SHADES[i]}
                    selected={selection.kind === 'holding' && selection.index === i}
                    onSelect={() => setSelection({ kind: 'holding', index: i })}
                    onOpenDetail={() => onSelectStock(i)}
                  />
                ))}

                {/* "기타 N개 종목" — 개별 기업이 아니라 나머지 합계 Summary Row라 Chevron이 없다 */}
                <StockRow
                  name={otherLabel.name}
                  pct={otherLabel.pct}
                  amountWon={won((amount * otherLabel.pct) / 100)}
                  dotColor={donutActiveIndex === 4 ? '#C6F04D' : SHADES[4]}
                  selected={selection.kind === 'other'}
                  onSelect={() => setSelection({ kind: 'other' })}
                />

                <button
                  onClick={() => setRestExpanded((v) => !v)}
                  className="self-start px-5 pt-2 text-base font-semibold text-navy"
                >
                  {restExpanded ? '접기 ↑' : '나머지 종목 보기 ↓'}
                </button>

                {restExpanded && (
                  <div className="flex flex-col gap-1 border-t border-[#F0F2ED] pt-1">
                    {restHoldings.map((h, j) => {
                      const index = j + 4; // ALL_HOLDINGS 상의 실제 인덱스
                      return (
                        <StockRow
                          key={h.name}
                          name={h.name}
                          pct={displayPct(h)}
                          amountWon={won((amount * displayPct(h)) / 100)}
                          dotColor={selection.kind === 'holding' && selection.index === index ? '#C6F04D' : SHADES[4]}
                          selected={selection.kind === 'holding' && selection.index === index}
                          onSelect={() => setSelection({ kind: 'holding', index })}
                          onOpenDetail={() => onSelectStock(index)}
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* 설명은 선택된 종목/집계 행에 붙는다 — 물방개가 왜 이 종목을 담았는지 생각해서 설명해주는 역할 */}
            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
              <img src="/character-thinking.png" alt="물방개" className="h-[68px] w-[68px] shrink-0 object-contain" />
              <div className="flex flex-col gap-3">
                <span className="text-[15px] font-semibold text-[#3F5222]">{sel.name} · {sel.pct.toFixed(1)}%</span>
                <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                  왜 {sel.name}을 {sel.pct.toFixed(1)}% 담았나요?
                </span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{sel.why}</p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-6 rounded-card bg-surface p-12">
            <h2 className="text-[26px] font-bold tracking-[-0.025em]">어떻게 운용할까요?</h2>
            <div className="grid grid-cols-2 gap-5">
              <ModeCard
                active={mode === 'manual'}
                onClick={() => setMode('manual')}
                badge="처음이라면 추천"
                title="확인하고 실행"
                flow={['AI가 알려줘요', '내가 확인해요', '실행']}
              />
              <ModeCard
                active={mode === 'auto'}
                onClick={() => setMode('auto')}
                title="자동으로 운용"
                flow={['AI가 판단해요', '자동 실행']}
              />
            </div>
          </section>

          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[17px] text-[#B9C2BA]">{strategyName} · {MOCK_TARGET_HOLDINGS.length}개 종목 · {mode === 'manual' ? '확인하고 실행' : '자동으로 운용'}</span>
              <span className="text-[32px] font-bold tracking-[-0.03em] text-white">{won(amount)}</span>
            </div>
            <button
              disabled={isStarting}
              onClick={async () => {
                setIsStarting(true);
                setStartError(null);
                try { await onStart(); }
                catch (error) { setStartError(error instanceof Error ? error.message : '가상계좌를 준비하지 못했습니다.'); }
                finally { setIsStarting(false); }
              }}
              className="shrink-0 rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isStarting ? '가상계좌 준비 중…' : '이대로 시작하기 →'}
            </button>
          </section>
          <p className="-mt-7 text-right text-sm text-subtle">
            화면의 금액 배분은 전략 시뮬레이션 예시이며, 실제 가상계좌 초기금은 Backend 정책값으로 생성됩니다.
          </p>
          {startError && <p role="alert" className="-mt-7 text-right text-sm font-semibold text-down">{startError}</p>}
        </div>
      </main>
    </div>
  );
}

/**
 * 종목 한 행 — PRIMARY: 이름/비중/금액 클릭 시 선정 이유 표시.
 * TERTIARY: 오른쪽 끝 Chevron 클릭 시 재무정보 상세로 이동 (별도 버튼이라 클릭이 서로 섞이지 않는다).
 * "기타 N개 종목" 집계 행은 onOpenDetail 을 넘기지 않아 Chevron 이 아예 표시되지 않는다.
 */
function StockRow({
  name, pct, amountWon, dotColor, selected, onSelect, onOpenDetail,
}: {
  name: string; pct: number; amountWon: string; dotColor: string;
  selected: boolean; onSelect: () => void; onOpenDetail?: () => void;
}) {
  return (
    <div className={`flex items-center rounded-2xl pl-5 pr-2 ${selected ? 'bg-[#F8FCEE]' : ''}`}>
      <button onClick={onSelect} className="flex flex-1 items-center gap-4 py-4 text-left">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: dotColor }} />
        <span className="flex-1 text-[18px] font-semibold tracking-[-0.02em]">{name}</span>
        <span className="text-[17px] font-bold">{pct.toFixed(1)}%</span>
        <span className="w-28 text-right text-base text-muted">{amountWon}</span>
      </button>
      {/* Action column 공간은 항상 확보한다 — Chevron이 없는 "기타 N개 종목" 행도 비중/금액이 다른 row와 같은 x축에 오도록 */}
      <div className="group relative flex h-8 w-8 shrink-0 items-center justify-center">
        {onOpenDetail && (
          <>
            <button
              type="button"
              aria-label={`${name} 재무정보 보기`}
              onClick={onOpenDetail}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-[#9CA3AF] outline-none hover:text-[#6B7280] focus-visible:text-[#6B7280]"
            >
              <ChevronRight size={16} />
            </button>
            <span
              role="tooltip"
              className="pointer-events-none absolute bottom-full right-0 z-10 mb-2 whitespace-nowrap rounded-md bg-navy px-2.5 py-1.5 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
            >
              재무정보 보기
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/** 운용 방식 카드 — 긴 설명 대신 mini-flow 로 3초 안에 차이를 보여준다 */
function ModeCard({
  active, onClick, badge, title, flow,
}: { active: boolean; onClick: () => void; badge?: string; title: string; flow: string[] }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-5 rounded-[20px] p-9 text-left ${
        active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
      }`}
    >
      {badge && <span className="self-start rounded-full bg-lime px-3 py-1.5 text-sm font-bold text-navy">{badge}</span>}
      <span className="text-2xl font-bold tracking-[-0.025em]">{title}</span>
      <div className="flex flex-wrap items-center gap-2">
        {flow.map((step, i) => (
          <span key={step} className="flex items-center gap-2">
            <span className="rounded-[10px] bg-surface px-3.5 py-2.5 text-[15px] font-semibold text-[#3F4A43]">{step}</span>
            {i < flow.length - 1 && <span className="text-[#A6AFA7]">→</span>}
          </span>
        ))}
      </div>
    </button>
  );
}
