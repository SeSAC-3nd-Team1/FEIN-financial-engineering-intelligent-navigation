import { useState } from 'react';
import { ChevronLeft } from 'lucide-react';
import { RISK_QUESTIONS } from '../data/riskQuestions';

interface Props {
  /** 백엔드 분석 결과가 Source of Truth이므로, 여기서는 답변만 넘기고 유형 판정은 호출부(App.tsx)에서 한다. */
  onComplete: (answers: number[]) => void;
  onExit: () => void;
  /** 실제 투자 시작 등 특정 목적으로 진입했을 때 상단에 보여줄 안내 문구 */
  notice?: string;
  /** onComplete 이후 백엔드 분석 응답을 기다리는 동안 true — 완료 버튼을 비활성화하고 로딩 문구를 보여준다 */
  isSubmitting?: boolean;
  /**
   * 'general': Home 등 일반 onboarding에서 진입 — "나에게 맞는 전략을 찾아볼까요?"
   * 'strategy': Strategy Detail "이 전략으로 시작하기"에서 진입 — 이미 고른 전략이 나와 맞는지 확인하는 맥락.
   * App.tsx가 이미 갖고 있던 postDiagnosisTarget(완료 후 목적지)을 그대로 재사용해 결정한다.
   */
  context?: 'general' | 'strategy';
}

const INTRO_COPY = {
  general: { title: '나에게 맞는 투자전략을 찾아볼까요?' },
  strategy: { title: '이 전략이 나에게 맞는지 확인해볼까요?' },
};

const DONE_COPY = {
  general: {
    title: '딱 맞는 전략을 찾았어요.',
    body: '답변을 바탕으로 투자전략을 비교했어요.',
    checklist: ['투자자 정보 확인 완료', '투자성향 분석 완료', '전략 추천 준비 완료'],
  },
  strategy: {
    title: '선택한 전략과 잘 맞는지 확인했어요.',
    body: '답변을 바탕으로 이 전략과의 적합도를 확인했어요.',
    checklist: ['투자자 정보 확인 완료', '투자성향 분석 완료', '전략 적합도 확인 완료'],
  },
};

type Phase = 'intro' | 'question' | 'done' | 'review';

/** Review 화면에서 문항을 묶어 보여줄 그룹 순서 — 문항 데이터의 등장 순서를 그대로 따른다 */
const REVIEW_GROUPS = Array.from(new Set(RISK_QUESTIONS.map((q) => q.reviewGroup)));

/** 투자자 정보 확인 — 인트로 → 8문항(한 화면 한 질문) → 완료 → 답변 확인(Review) */
export default function RiskProfile({ onComplete, onExit, notice, isSubmitting, context = 'general' }: Props) {
  const [phase, setPhase] = useState<Phase>('intro');
  const introCopy = INTRO_COPY[context];
  const doneCopy = DONE_COPY[context];
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(RISK_QUESTIONS.length).fill(null));
  // null이 아니면 "Review 화면에서 수정하러 들어온 상태" — 답변 후 질문을 이어가지 않고 Review로 돌아간다
  const [reviewEditIndex, setReviewEditIndex] = useState<number | null>(null);

  const total = RISK_QUESTIONS.length;
  const q = RISK_QUESTIONS[step];
  const picked = answers[step];
  const isLast = step === total - 1;
  const isEditingFromReview = reviewEditIndex !== null;

  const answer = (i: number) => {
    setAnswers((prev) => prev.map((v, idx) => (idx === step ? i : v)));
  };

  const backToReview = () => {
    setReviewEditIndex(null);
    setPhase('review');
  };

  const next = () => {
    if (picked === null) return;
    if (isEditingFromReview) { backToReview(); return; }
    if (isLast) setPhase('done');
    else setStep((s) => s + 1);
  };

  const prev = () => {
    if (isEditingFromReview) { backToReview(); return; }
    if (step === 0) setPhase('intro');
    else setStep((s) => s - 1);
  };

  const editFromReview = (index: number) => {
    setReviewEditIndex(index);
    setStep(index);
    setPhase('question');
  };

  const finish = () => {
    const finalAnswers = answers as number[]; // 모든 문항 응답 완료 후에만 도달 가능
    onComplete(finalAnswers);
  };

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center gap-6 px-16">
        <button onClick={onExit} className="flex shrink-0 items-center gap-2">
          <img src="/main_logo_2.png" alt="FE!N" className="h-16 w-auto object-contain" />
        </button>

        {phase === 'question' && (
          <div className="flex flex-1 items-center gap-7">
            <button onClick={prev} className="flex shrink-0 items-center gap-1.5 text-[15px] font-semibold text-muted">
              <ChevronLeft size={18} /> 뒤로가기
            </button>
            <div className="flex flex-1 items-center gap-4">
              <span className="shrink-0 text-[15px] font-semibold text-muted">투자자 정보 확인 · {step + 1}/{total}</span>
              <div className="h-1.5 w-full flex-1 rounded-full bg-line">
                <div
                  className="h-full rounded-full bg-lime transition-all"
                  style={{ width: `${((step + 1) / total) * 100}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </header>

      {phase === 'intro' && (
        <main className="flex flex-col items-center gap-7 px-8 py-28">
          {notice && (
            <span className="rounded-full bg-[#FDF1E0] px-5 py-3 text-base font-semibold text-warn">
              {notice}
            </span>
          )}
          <h1 className="max-w-[620px] text-center text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
            {introCopy.title}
          </h1>
          <p className="max-w-[560px] text-center text-[19px] leading-8 text-muted">
            몇 가지 질문으로 투자 경험과 목표, 감당할 수 있는 위험 수준을 확인할게요.<br />
            답변을 바탕으로 나에게 맞는 투자전략을 찾는 데 활용해요.
          </p>
          <span className="rounded-full bg-surface px-5 py-3 text-base font-semibold text-[#3F4A43]">약 2분 · {total}문항</span>
          <button onClick={() => setPhase('question')} className="mt-3 rounded-field bg-lime px-11 py-5 text-[19px] font-bold text-navy">
            투자자 정보 확인하기
          </button>
          <p className="text-base text-subtle">입력한 정보는 투자성향 확인 및 맞춤형 전략 제공에 활용돼요.</p>
        </main>
      )}

      {phase === 'question' && (
        <main className="mx-auto flex w-[760px] flex-col gap-10 py-16">
          <div className="flex flex-col gap-4">
            <h1 className="whitespace-pre-line text-[38px] font-bold leading-[54px] tracking-[-0.035em]">{q.q}</h1>
            {q.support && <p className="text-lg leading-[30px] text-muted">{q.support}</p>}
          </div>

          <div className="flex flex-col gap-3">
            {q.options.map((o, i) => (
              <button
                key={o.title}
                onClick={() => answer(i)}
                className={`flex items-center gap-5 rounded-[20px] px-8 py-7 text-left ${
                  picked === i ? 'bg-[#F8FCEE] shadow-[0_0_0_2px_#C6F04D_inset]' : 'bg-surface shadow-[0_0_0_1px_#E5E9E3_inset]'
                }`}
              >
                <div className="flex flex-1 flex-col gap-2">
                  <span className="text-[22px] font-bold tracking-[-0.02em]">{o.title}</span>
                  {o.desc && <span className="text-[17px] leading-7 text-muted">{o.desc}</span>}
                </div>
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[15px] font-bold ${
                  picked === i ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-white'
                }`}>✓</span>
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between gap-5 pt-2">
            <button onClick={prev} className="rounded-field bg-[#F4F6F1] px-7 py-[18px] text-[17px] font-semibold text-[#3F4A43]">
              이전
            </button>
            <button
              onClick={next}
              disabled={picked === null}
              className="rounded-field px-10 py-[18px] text-lg font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
            >
              {isEditingFromReview ? '리뷰로 돌아가기' : isLast ? '결과 확인하기' : '다음'}
            </button>
          </div>
          <p className="text-center text-base text-subtle">너무 고민하지 않아도 괜찮아요. 평소 느낌대로 골라주세요.</p>
        </main>
      )}

      {phase === 'done' && (
        <main className="flex flex-col items-center gap-8 py-32">
          <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[22px] bg-lime text-[32px] text-navy">✓</div>
          <h1 className="text-center text-[44px] font-bold leading-[62px] tracking-[-0.035em]">{doneCopy.title}</h1>
          <p className="text-[19px] leading-8 text-muted">{doneCopy.body}</p>
          <div className="flex flex-col gap-3.5 rounded-card bg-surface px-11 py-9 text-lg text-[#3F4A43]">
            {doneCopy.checklist.map((t) => (
              <span key={t} className="flex items-center gap-3">
                <span className="font-bold text-[#2E9B65]">✓</span>{t}
              </span>
            ))}
          </div>
          <button onClick={() => setPhase('review')} className="rounded-field bg-lime px-10 py-5 text-[19px] font-bold text-navy">
            답변 확인하기 →
          </button>
        </main>
      )}

      {phase === 'review' && (
        <main className="mx-auto flex w-[760px] flex-col gap-10 py-16">
          <div className="flex flex-col gap-4">
            <h1 className="text-[38px] font-bold leading-[54px] tracking-[-0.035em]">입력한 내용을 확인해주세요</h1>
            <p className="text-lg leading-[30px] text-muted">
              투자성향을 확인하기 전에 답변한 내용을 한 번 확인해주세요.<br />
              잘못 입력한 내용이 있다면 수정할 수 있어요.
            </p>
          </div>

          {notice && (
            <div role="alert" className="rounded-[16px] bg-[#FDF1E0] px-6 py-4 text-base font-semibold text-warn">
              {notice}
            </div>
          )}

          <div className="flex flex-col gap-6">
            {REVIEW_GROUPS.map((group) => (
              <div key={group} className="flex flex-col gap-1 rounded-card bg-surface p-9">
                <span className="pb-3 text-[17px] font-bold tracking-[-0.02em]">{group}</span>
                {RISK_QUESTIONS.map((rq, i) => (rq.reviewGroup === group ? (
                  <div key={rq.reviewLabel} className="flex items-center justify-between gap-4 border-t border-[#F0F2ED] py-4">
                    <span className="w-[160px] shrink-0 text-[15px] text-muted">{rq.reviewLabel}</span>
                    <span className="flex-1 text-[17px] font-semibold text-ink">
                      {answers[i] !== null ? rq.options[answers[i] as number].title : '-'}
                    </span>
                    <button onClick={() => editFromReview(i)} className="shrink-0 text-sm font-semibold text-navy underline">
                      수정
                    </button>
                  </div>
                ) : null))}
              </div>
            ))}
          </div>

          <button
            onClick={finish}
            disabled={isSubmitting}
            className="rounded-field bg-lime py-5 text-[19px] font-bold text-navy disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7]"
          >
            {isSubmitting ? '결과 분석 중...' : '이 내용으로 결과 확인하기'}
          </button>
        </main>
      )}
    </div>
  );
}
