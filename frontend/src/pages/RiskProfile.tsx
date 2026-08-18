import { useState } from 'react';
import { RISK_QUESTIONS, SPECTRUM_LABELS } from '../data/riskQuestions';

interface Props {
  onComplete: () => void;
  onExit: () => void;
}

type Phase = 'intro' | 'question' | 'done';

/** 01 투자성향 진단 — 인트로 → 5문항(한 화면 한 질문) → 완료 */
export default function RiskProfile({ onComplete, onExit }: Props) {
  const [phase, setPhase] = useState<Phase>('intro');
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(RISK_QUESTIONS.length).fill(null));

  const q = RISK_QUESTIONS[step];
  const picked = answers[step];
  const isLast = step === RISK_QUESTIONS.length - 1;

  const answer = (i: number) => {
    setAnswers((prev) => prev.map((v, idx) => (idx === step ? i : v)));
  };

  const next = () => {
    if (picked === null) return;
    if (isLast) setPhase('done');
    else setStep((s) => s + 1);
  };

  const prev = () => {
    if (step === 0) setPhase('intro');
    else setStep((s) => s - 1);
  };

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center justify-between px-16">
        <button onClick={onExit} className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-[7px] bg-navy" />
          <span className="text-[19px] font-bold tracking-[-0.02em]">물림방지</span>
        </button>
        {phase === 'question' && (
          <div className="flex items-center gap-4">
            {/* 진행 표시는 숫자 퍼센트 대신 점 5개 */}
            <div className="flex gap-2">
              {RISK_QUESTIONS.map((_, i) => (
                <span key={i} className={`h-2.5 w-2.5 rounded-full ${i <= step ? 'bg-lime' : 'bg-[#E0E4DC]'}`} />
              ))}
            </div>
            <span className="text-[15px] text-muted">{step + 1} / {RISK_QUESTIONS.length}</span>
          </div>
        )}
      </header>

      {phase === 'intro' && (
        <main className="flex flex-col items-center gap-7 py-32">
          <h1 className="text-center text-[44px] font-bold leading-[62px] tracking-[-0.035em]">
            이제 나에게 맞는<br />투자전략을 찾아볼게요.
          </h1>
          <p className="max-w-[620px] text-center text-[19px] leading-8 text-muted">
            정답은 없어요. 평소 투자할 때 어떤 선택을 할지 편하게 골라주세요.
          </p>
          <span className="rounded-full bg-surface px-5 py-3 text-base font-semibold text-[#3F4A43]">약 1분 · 5문항</span>
          <button onClick={() => setPhase('question')} className="mt-3 rounded-field bg-lime px-11 py-5 text-[19px] font-bold text-navy">
            진단 시작하기
          </button>
          <p className="text-base text-subtle">결과는 전략 추천에만 활용돼요.</p>
        </main>
      )}

      {phase === 'question' && (
        <main className="mx-auto flex w-[760px] flex-col gap-10 py-16">
          <div className="flex flex-col gap-4">
            <span className="text-base font-semibold text-muted">{step + 1} / {RISK_QUESTIONS.length}</span>
            <h1 className="whitespace-pre-line text-[38px] font-bold leading-[54px] tracking-[-0.035em]">{q.q}</h1>
            <p className="text-lg leading-[30px] text-muted">{q.support}</p>
          </div>

          {/* Q1: 숫자를 상황으로 보여주는 작은 비주얼 */}
          {q.visual === 'loss' && (
            <div className="flex items-center justify-center gap-8 rounded-card bg-surface p-10">
              <span className="text-[30px] font-bold tracking-[-0.03em] text-muted">1,000,000원</span>
              <span className="text-2xl text-[#A6AFA7]">→</span>
              <span className="text-[38px] font-bold tracking-[-0.035em]">850,000원</span>
              <span className="rounded-full bg-[#EAF1FD] px-4 py-2.5 text-lg font-bold text-down">-15%</span>
            </div>
          )}

          {/* Q5: 5단계 스펙트럼 */}
          {q.spectrum && (
            <div className="flex flex-col gap-7 rounded-card bg-surface p-12">
              <div className="flex items-center justify-between text-[17px] font-semibold text-muted">
                <span>일단 안전하게</span>
                <span>기회를 찾아보기</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                {[0, 1, 2, 3, 4].map((i) => (
                  <button
                    key={i}
                    onClick={() => answer(i)}
                    className={`h-14 flex-1 rounded-2xl ${picked !== null && i <= picked ? 'bg-lime' : 'bg-[#F0F2ED]'}`}
                  />
                ))}
              </div>
              <p className="text-center text-[17px] text-[#3F4A43]">
                {picked === null ? '가장 가까운 위치를 눌러주세요' : SPECTRUM_LABELS[picked]}
              </p>
            </div>
          )}

          {/* Q1~Q4: 큰 선택 카드 */}
          {q.options && (
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
                    <span className="text-[17px] leading-7 text-muted">{o.desc}</span>
                  </div>
                  <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[15px] font-bold ${
                    picked === i ? 'bg-lime text-navy' : 'bg-[#F4F6F1] text-white'
                  }`}>✓</span>
                </button>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-5 pt-2">
            <button onClick={prev} className="rounded-field bg-[#F4F6F1] px-7 py-[18px] text-[17px] font-semibold text-[#3F4A43]">
              이전
            </button>
            <button
              onClick={next}
              disabled={picked === null}
              className="rounded-field px-10 py-[18px] text-lg font-bold disabled:cursor-default disabled:bg-[#E8EBE5] disabled:text-[#A6AFA7] enabled:bg-lime enabled:text-navy"
            >
              {isLast ? '결과 보기' : '다음'}
            </button>
          </div>
          <p className="text-center text-base text-subtle">너무 고민하지 않아도 괜찮아요. 평소 느낌대로 골라주세요.</p>
        </main>
      )}

      {phase === 'done' && (
        <main className="flex flex-col items-center gap-8 py-32">
          <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[22px] bg-lime text-[32px] text-navy">✓</div>
          <h1 className="text-center text-[44px] font-bold leading-[62px] tracking-[-0.035em]">딱 맞는 전략을 찾았어요.</h1>
          <p className="text-[19px] leading-8 text-muted">답변을 바탕으로 투자전략을 비교했어요.</p>
          <div className="flex flex-col gap-3.5 rounded-card bg-surface px-11 py-9 text-lg text-[#3F4A43]">
            {['성향 분석 완료', '전략 비교 완료', '추천 준비 완료'].map((t) => (
              <span key={t} className="flex items-center gap-3">
                <span className="font-bold text-[#2E9B65]">✓</span>{t}
              </span>
            ))}
          </div>
          <button onClick={onComplete} className="rounded-field bg-lime px-10 py-5 text-[19px] font-bold text-navy">
            결과 보기 →
          </button>
        </main>
      )}
    </div>
  );
}
