import { useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import Header from '../components/Header';
import { ALL_HOLDINGS } from '../data/holdings';
import { estimateAnnualFee, INVESTMENT_FEES, type OperationMode } from '../data/fees';
import { won } from '../lib/validation';
import type { Screen } from '../types';

interface Props {
  userName: string;
  /** RiskResult/StrategyDetail 에서 선택한 전략의 표시 이름 (예: "저변동성 전략") */
  strategyName: string;
  onNavigate: (s: Screen) => void;
  onStart: () => void;
}

const PRESETS = [100_000, 500_000, 1_000_000, 5_000_000];
/** 도넛 색: Deep Navy 계열 + 중립. 선택된 조각만 라임 */
const SHADES = ['#18243A', '#2E4160', '#4A5F80', '#6C819E', '#C3CBC4'];

export default function StartInvesting({ userName, strategyName, onNavigate, onStart }: Props) {
  const [amount, setAmount] = useState(1_000_000);
  const [custom, setCustom] = useState<string | null>(null); // null = 직접 입력 꺼짐
  const [selected, setSelected] = useState(0);
  const [mode, setMode] = useState<OperationMode>('manual');

  /** 04는 전략 목표 비중으로 새로 담는다 (target 이 있으면 그 값) */
  const slices = useMemo(() => {
    const top = ALL_HOLDINGS.slice(0, 4).map((h) => ({ name: h.name, pct: h.target ?? h.pct, why: h.why }));
    const restPct = Math.round((100 - top.reduce((a, h) => a + h.pct, 0)) * 10) / 10;
    return [...top, { name: `기타 ${ALL_HOLDINGS.length - 4}개 종목`, pct: restPct, why: '한 종목에 쏠리지 않도록 나머지를 고르게 나눠 담았어요.' }];
  }, []);

  const sel = slices[selected];

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
                      onClick={(_, i) => setSelected(i)}
                    >
                      {slices.map((_, i) => (
                        /* 선택된 조각만 라임 — 나머지는 네이비 계열 */
                        <Cell key={i} fill={i === selected ? '#C6F04D' : SHADES[i]} cursor="pointer" />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1">
                  <span className="text-[32px] font-bold tracking-[-0.035em]">
                    {(amount / 10000).toLocaleString('ko-KR')}만원
                  </span>
                  <span className="text-base text-muted">{ALL_HOLDINGS.length}개 종목</span>
                </div>
              </div>

              <div className="flex flex-1 flex-col gap-1">
                {slices.map((h, i) => (
                  <button
                    key={h.name}
                    onClick={() => setSelected(i)}
                    className={`flex items-center gap-4 rounded-2xl px-5 py-4 text-left ${i === selected ? 'bg-[#F8FCEE]' : ''}`}
                  >
                    <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: i === selected ? '#C6F04D' : SHADES[i] }} />
                    <span className="flex-1 text-[18px] font-semibold tracking-[-0.02em]">{h.name}</span>
                    <span className="text-[17px] font-bold">{h.pct.toFixed(1)}%</span>
                    <span className="w-28 text-right text-base text-muted">{won((amount * h.pct) / 100)}</span>
                  </button>
                ))}
                <span className="px-5 pt-2 text-base font-semibold text-navy">나머지 종목 보기 →</span>
              </div>
            </div>

            {/* AI 설명은 선택된 종목에 붙는다 */}
            <div className="flex gap-5 rounded-[20px] bg-[#F8FCEE] px-10 py-9">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-lime text-lg text-navy">✦</div>
              <div className="flex flex-col gap-3">
                <span className="text-[15px] font-semibold text-[#3F5222]">{sel.name} · {sel.pct.toFixed(1)}%</span>
                <span className="text-[22px] font-bold leading-[34px] tracking-[-0.025em]">
                  왜 {sel.name}을 {sel.pct.toFixed(1)}% 담았나요?
                </span>
                <p className="max-w-[720px] text-lg leading-[30px] text-[#3F4A43]">{sel.why}</p>
                <span className="pt-1 text-base font-semibold text-navy">더 자세히 물어보기 →</span>
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
                flow={['물방개가 제안해요', '내가 확인해요', '실행']}
                mode="manual"
                amount={amount}
              />
              <ModeCard
                active={mode === 'auto'}
                onClick={() => setMode('auto')}
                title="자동으로 운용"
                flow={['물방개가 관리해요', '자동 실행']}
                mode="auto"
                amount={amount}
              />
            </div>
          </section>

          <section className="flex items-center justify-between gap-8 rounded-card bg-navy px-12 py-11">
            <div className="flex flex-col gap-2.5">
              <span className="text-[17px] text-[#B9C2BA]">{strategyName} · {ALL_HOLDINGS.length}개 종목 · {mode === 'manual' ? '확인하고 실행' : '자동으로 운용'}</span>
              <span className="text-[32px] font-bold tracking-[-0.03em] text-white">{won(amount)}</span>
            </div>
            <button onClick={onStart} className="shrink-0 rounded-field bg-lime px-9 py-5 text-lg font-bold text-navy">
              이대로 시작하기 →
            </button>
          </section>

          <section className="flex flex-col gap-2 rounded-card bg-surface p-12 shadow-[0_0_0_1px_#E5E9E3_inset]">
            <h2 className="text-[22px] font-bold tracking-[-0.025em]">투자 전 궁금한 점이 있나요?</h2>
            <p className="pb-3 text-[15px] text-muted">궁금한 항목을 선택하면 자세히 알려드려요.</p>
            <FaqAccordion amount={amount} />
          </section>
        </div>
      </main>
    </div>
  );
}

/**
 * 운용 방식 카드 — 긴 설명 대신 mini-flow 로 3초 안에 차이를 보여주고, 그 아래 이용 수수료를 짧게 덧붙인다.
 * 카드 전체는 여전히 클릭해서 선택할 수 있지만(전체를 덮는 투명 오버레이 버튼), 수수료 옆 Info 아이콘은
 * 별도의 작은 버튼이라 겹쳐 쌓을 수 없어(button 안에 button 불가) content 레이어를 오버레이보다 위에 두고
 * 장식용 텍스트만 pointer-events-none 처리해 클릭이 오버레이로 통과하게 한다.
 */
function ModeCard({
  active, onClick, badge, title, flow, mode, amount,
}: { active: boolean; onClick: () => void; badge?: string; title: string; flow: string[]; mode: OperationMode; amount: number }) {
  const feeRate = INVESTMENT_FEES[mode];
  const feeAmount = estimateAnnualFee(amount, mode);
  const amountLabel = `${(amount / 10000).toLocaleString('ko-KR')}만원`;

  return (
    <div
      className={`relative flex flex-col gap-5 rounded-[20px] p-9 text-left ${
        active ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-canvas shadow-[0_0_0_1px_#E5E9E3_inset]'
      }`}
    >
      <button type="button" onClick={onClick} aria-label={title} className="absolute inset-0 z-0 rounded-[20px]" />

      <div className="relative z-10 flex flex-col gap-5 pointer-events-none">
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
      </div>

      <div className="relative z-10 flex items-center justify-between gap-4 border-t border-[#E5E9E3] pt-5 pointer-events-none">
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-muted">이용 수수료</span>
          <FeeInfoTooltip />
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-base font-bold text-ink">연 {(feeRate * 100).toFixed(1)}%</span>
          <span className="text-xs text-subtle">{amountLabel} 기준 연 약 {won(feeAmount)}</span>
        </div>
      </div>
    </div>
  );
}

/** 이용 수수료 옆 짧은 안내 — hover(desktop)/tap(mobile)/focus(keyboard) 모두 지원 */
function FeeInfoTooltip() {
  const [hoverCapable] = useState(
    () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches,
  );
  const [open, setOpen] = useState(false);
  const pointerActivated = useRef(false);
  const markPointer = () => { pointerActivated.current = true; };

  return (
    <span className="relative z-10 inline-flex pointer-events-auto">
      <button
        type="button"
        aria-label="이용 수수료 설명 보기"
        aria-expanded={open}
        onMouseDown={markPointer}
        onTouchStart={markPointer}
        onMouseEnter={() => hoverCapable && setOpen(true)}
        onMouseLeave={() => hoverCapable && setOpen(false)}
        onFocus={() => {
          if (pointerActivated.current) { pointerActivated.current = false; return; }
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onClick={() => {
          if (hoverCapable) { setOpen(true); return; }
          setOpen((o) => !o);
        }}
        className="flex h-5 w-5 items-center justify-center rounded-full text-subtle hover:text-navy"
      >
        <Info size={14} />
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute bottom-full left-1/2 z-10 mb-2 w-[220px] -translate-x-1/2 rounded-[12px] bg-navy px-4 py-3 text-[13px] leading-5 text-white shadow-[0_8px_24px_rgba(24,36,58,0.25)]"
        >
          실제 수수료는 잔고와 이용 기간 등에 따라 달라질 수 있어요.
        </div>
      )}
    </span>
  );
}

interface FaqEntry { id: string; question: string; answer: ReactNode }

/** MVP에 실제로 구현된 기능 범위에 맞춘 FAQ 답변 — 없는 기능을 있다고 서술하지 않는다 */
function buildFaqEntries(amount: number): FaqEntry[] {
  const manualFee = estimateAnnualFee(amount, 'manual');
  const autoFee = estimateAnnualFee(amount, 'auto');
  const amountLabel = `${(amount / 10000).toLocaleString('ko-KR')}만원`;

  return [
    {
      id: 'fee',
      question: '수수료는 어떻게 계산되나요?',
      answer: (
        <div className="flex flex-col gap-4">
          <p>선택한 운용 방식에 따라 이용 수수료가 달라져요.</p>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1 rounded-[12px] bg-canvas px-5 py-4">
              <span className="text-[13px] font-semibold text-ink">확인하고 실행</span>
              <span className="text-lg font-bold text-navy">연 {(INVESTMENT_FEES.manual * 100).toFixed(1)}%</span>
              <span className="text-xs text-subtle">{amountLabel} 기준 연 약 {won(manualFee)}</span>
              <p className="pt-1 text-[13px] text-muted">물방개가 제안한 내용을 사용자가 직접 확인한 후 실행해요.</p>
            </div>
            <div className="flex flex-col gap-1 rounded-[12px] bg-canvas px-5 py-4">
              <span className="text-[13px] font-semibold text-ink">자동으로 운용</span>
              <span className="text-lg font-bold text-navy">연 {(INVESTMENT_FEES.auto * 100).toFixed(1)}%</span>
              <span className="text-xs text-subtle">{amountLabel} 기준 연 약 {won(autoFee)}</span>
              <p className="pt-1 text-[13px] text-muted">포트폴리오 관리와 리밸런싱 등을 자동으로 진행해요.</p>
            </div>
          </div>
          <div className="flex flex-col gap-1 text-xs text-subtle">
            <span>실제 수수료는 잔고와 이용 기간 등에 따라 달라질 수 있어요.</span>
            <span>실제 매매 과정에서는 거래비용 및 세금 등 별도 비용이 발생할 수 있어요.</span>
            <span>현재 표시된 이용 수수료는 프로토타입을 위한 가상의 정책입니다.</span>
          </div>
        </div>
      ),
    },
    {
      id: 'diff',
      question: '확인하고 실행과 자동으로 운용은 무엇이 다른가요?',
      answer: (
        <div className="flex flex-col gap-3">
          <p><b className="text-ink">확인하고 실행</b> · 물방개가 투자 또는 리밸런싱을 제안해요. 사용자가 내용을 확인한 뒤 실행 여부를 결정해요.</p>
          <p><b className="text-ink">자동으로 운용</b> · 물방개가 포트폴리오를 관리하고, 운용 기준에 따라 필요한 조정을 자동으로 실행해요.</p>
          <p>직접 확인하고 결정하고 싶다면 &apos;확인하고 실행&apos;, 운용을 맡기고 싶다면 &apos;자동으로 운용&apos;을 선택할 수 있어요.</p>
        </div>
      ),
    },
    {
      id: 'rebalance-timing',
      question: '자동 운용은 언제 종목을 사고팔아요?',
      // MOCK — 실제 자동 매매 정책/트리거가 아직 구현되어 있지 않아, 조건을 구체적인 사실처럼 서술하지 않는다.
      answer: (
        <div className="flex flex-col gap-2">
          <p>자동 운용은 선택한 전략의 목표 비중에서 포트폴리오가 벗어나거나, 전략의 리밸런싱 조건이 충족될 때 조정을 검토해요.</p>
          <p>실제 매매 조건과 주기는 운용 정책에 따라 달라질 수 있어요.</p>
        </div>
      ),
    },
    {
      id: 'change-mode',
      question: '투자 중에도 운용 방식을 바꿀 수 있나요?',
      // 현재 실제 구현된 운용 방식 변경 기능이 없어, 가능하다고 서술하지 않는다.
      answer: <p>현재 MVP에서는 투자 시작 후 운용 방식 변경 기능을 제공하지 않아요.</p>,
    },
    {
      id: 'stop',
      question: '투자를 중단하면 어떻게 되나요?',
      // 현재 실제 출금/해지 flow가 없고 정책도 확정 전이라, 임의의 정책을 서술하지 않는다.
      answer: <p>현재 MVP에서는 투자 중단(출금) 기능을 제공하지 않아요. 실제 서비스 출시 전 정책 확정이 필요해요.</p>,
    },
    {
      id: 'loss',
      question: '투자 손실이 발생할 수도 있나요?',
      answer: (
        <div className="flex flex-col gap-2">
          <p>네. 투자 과정에서는 원금 손실이 발생할 수 있어요.</p>
          <p>백테스트와 과거 성과는 미래 수익을 보장하지 않아요.</p>
          <p>전략을 시작하기 전에 백테스트와 위험지표를 함께 확인해주세요.</p>
        </div>
      ),
    },
  ];
}

/** 투자 전 FAQ — single-open accordion. Lime은 핵심 수치에만 쓰고 질문 텍스트/row 배경에는 쓰지 않는다 */
function FaqAccordion({ amount }: { amount: number }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const entries = useMemo(() => buildFaqEntries(amount), [amount]);

  return (
    <div className="flex flex-col">
      {entries.map((entry, i) => {
        const isOpen = openId === entry.id;
        return (
          <div key={entry.id} className={i > 0 ? 'border-t border-[#F0F2ED]' : ''}>
            <button
              onClick={() => setOpenId(isOpen ? null : entry.id)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-4 py-5 text-left"
            >
              <span className="text-[15px] font-semibold text-ink">{entry.question}</span>
              {isOpen
                ? <ChevronUp size={18} className="shrink-0 text-subtle" />
                : <ChevronDown size={18} className="shrink-0 text-subtle" />}
            </button>
            {isOpen && <div className="pb-6 text-[14px] leading-[1.6] text-[#3F4A43]">{entry.answer}</div>}
          </div>
        );
      })}
    </div>
  );
}
