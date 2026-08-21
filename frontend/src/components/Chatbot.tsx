import { useEffect, useRef, useState } from 'react';
import { RotateCcw, X, ArrowUp } from 'lucide-react';
import type { ChatMessage } from '../types';

/** 빠른 질문과 목 응답 쌍 */
const QUICK_QA: [string, string][] = [
  ['PER이 무엇인가요?', '지금 벌고 있는 이익으로 주가를 몇 년이면 회수할 수 있는지 보는 값이에요. 낮으면 이익 대비 싸게 거래된다는 뜻이지만, 성장하는 회사는 원래 높게 거래되는 경우가 많아요.'],
  ['PBR이 무엇인가요?', '회사가 가진 순자산에 비해 주가가 몇 배인지 보는 값이에요. 1배보다 낮으면 장부상 재산보다 싸게 거래되고 있다는 뜻이에요.'],
  ['ROE가 무엇인가요?', '회사가 자기 돈으로 얼마나 잘 벌었는지 보는 값이에요. 높을수록 같은 자본으로 더 많은 이익을 냈다는 뜻이에요.'],
];

const FALLBACK =
  '아직 준비 중인 답변이에요. 지표나 종목 이름을 넣어 물어보시면 쉬운 말로 풀어드릴게요.';

let seq = 0;
const nextId = () => `m${++seq}`;

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  /** 새 메시지가 쌓이면 항상 최신 대화가 보이도록 스크롤 */
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  /** 질문을 붙이고 500ms 뒤 목 응답을 붙인다 (스트리밍 흉내) */
  const ask = (question: string) => {
    const answer = QUICK_QA.find(([q]) => q === question)?.[1] ?? FALLBACK;
    setMessages((prev) => [...prev, { id: nextId(), role: 'user', text: question }]);
    window.setTimeout(() => {
      setMessages((prev) => [...prev, { id: nextId(), role: 'bot', text: answer }]);
    }, 500);
  };

  const submit = () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    ask(text);
  };

  /** 새로고침: 대화를 비워 캐릭터 + 인사말 + 빠른 질문 화면으로 되돌린다 */
  const reset = () => setMessages([]);

  const started = messages.length > 0;

  return (
    <>
      {open && (
        <section
          /* 팝업은 FAB 바로 위 고정, 화면의 30% 폭 */
          className="fixed bottom-[104px] right-8 z-[600] flex h-[min(78vh,calc(100vh-136px))] w-[30vw] min-w-[360px] flex-col overflow-hidden rounded-[20px] bg-surface shadow-[0_20px_60px_rgba(24,36,58,0.18)]"
        >
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <span className="text-[17px] font-bold tracking-[-0.02em]">물방개에게 물어보기</span>
            <div className="flex items-center gap-1.5">
              {/* 픽토그램 컨트롤 */}
              <button aria-label="새로고침" onClick={reset} className="rounded-lg p-2 text-muted hover:bg-canvas">
                <RotateCcw size={17} />
              </button>
              <button aria-label="닫기" onClick={() => setOpen(false)} className="rounded-lg p-2 text-muted hover:bg-canvas">
                <X size={18} />
              </button>
            </div>
          </div>

          <div ref={scrollRef} className="flex flex-1 flex-col gap-3 overflow-auto px-5 py-2.5">
            {!started && (
              /* 초기 상태: 캐릭터 이미지 → 인사말 → 빠른 질문 3개를 대화창 가운데 배치 */
              <div className="m-auto flex w-full flex-col items-center gap-1.5">
                <div className="flex w-full flex-col items-center gap-1.5">
                  <img src="/character-analyze.png" alt="물방개 캐릭터" className="block h-20 w-20 object-contain" />
                  <span className="text-center text-base font-bold leading-6 tracking-[-0.02em]">
                    물방개에게 주식을 쉽게 물어보세요
                  </span>
                </div>
                <div className="flex w-full max-w-[280px] flex-col gap-2 pt-1.5">
                  {QUICK_QA.map(([q]) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      className="rounded-field bg-lime px-3.5 py-2.5 text-sm font-semibold text-[#3F5222] shadow-[0_0_0_1px_#E3EFC4_inset]"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <span
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-[24px] ${
                    m.role === 'user' ? 'bg-navy text-white' : 'bg-canvas text-[#3F4A43]'
                  }`}
                >
                  {m.text}
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2.5 border-t border-line px-5 pb-4 pt-3.5">
            {started && (
              /* 대화 중에는 빠른 질문을 입력창 위 칩으로 유지 */
              <div className="flex flex-wrap gap-2">
                {QUICK_QA.map(([q]) => (
                  <button
                    key={q}
                    onClick={() => ask(q)}
                    className="rounded-full bg-[#F8FCEE] px-3.5 py-2.5 text-[13px] font-semibold text-[#3F5222] shadow-[0_0_0_1px_#E3EFC4_inset]"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                placeholder="질문을 입력하세요..."
                className="flex-1 rounded-field bg-canvas px-3.5 py-3 text-[15px] outline-none"
              />
              <button
                aria-label="전송"
                onClick={submit}
                className="rounded-field bg-lime p-3 text-navy disabled:opacity-40"
                disabled={!input.trim()}
              >
                <ArrowUp size={18} />
              </button>
            </div>
          </div>
        </section>
      )}

      {/* FAB: character-master.png 를 원형 프레임 안에 렌더 */}
      <button
        title="물방개에게 물어보기"
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-8 right-8 z-[600] flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-lime shadow-[0_10px_28px_rgba(24,36,58,0.24)]"
      >
        <img src="/character-master.png" alt="물방개" className="h-12 w-12 object-contain" />
      </button>
    </>
  );
}
