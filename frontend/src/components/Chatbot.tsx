import { useEffect, useRef, useState } from "react";
import { RotateCcw, X, ArrowUp } from "lucide-react";
import {
  ApiError,
  createChatMessageApi,
  type ChatHistoryMessageRequest,
  type ChatScreenContextRequest,
} from "../lib/backendApi";
import { useAuthStore } from "../store/authStore";
import { chatConversationBoundaryKey } from "../lib/chatSession";
import type { ChatMessage, Screen } from "../types";

const QUICK_QUESTIONS = [
  "PER이 무엇인가요?",
  "PBR이 무엇인가요?",
  "ROE가 무엇인가요?",
];

let seq = 0;
const nextId = () => `m${++seq}`;

const toHistory = (messages: ChatMessage[]): ChatHistoryMessageRequest[] =>
  messages.slice(-10).map((message) => ({
    role: message.role === "user" ? "user" : "assistant",
    content: message.text,
  }));

interface Props {
  screen: Screen;
  stockCode?: string;
  strategyId?: string;
  accountId?: string;
}

export default function Chatbot({
  screen,
  stockCode,
  strategyId,
  accountId,
}: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{
    question: string;
    message: string;
  } | null>(null);
  const accessToken = useAuthStore((state) => state.accessToken);
  const conversationBoundary = chatConversationBoundaryKey(
    accessToken,
    accountId,
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);
  const requestPendingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, loading, error]);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  const cancelRequest = () => {
    requestIdRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    requestPendingRef.current = false;
    setLoading(false);
  };

  // 인증 토큰 또는 계좌가 바뀌면 사용자/계좌 대화 경계가 바뀐 것이다.
  // 이전 history가 새 context와 결합되지 않도록 진행 중인 요청과 UI 상태를 함께 폐기한다.
  useEffect(() => {
    cancelRequest();
    setMessages([]);
    setError(null);
    setInput("");
  }, [conversationBoundary]);

  const screenContext = (): ChatScreenContextRequest => ({
    screen,
    ...(screen === "stock" && stockCode ? { stock_code: stockCode } : {}),
    ...(["strategy", "start", "invest-terms", "invest-confirm"].includes(
      screen,
    ) && strategyId
      ? { strategy_id: strategyId }
      : {}),
    ...([
      "dashboard",
      "portfolio",
      "portfolio-detail",
      "stock",
      "transactions",
      "transaction-detail",
      "rebalance-alerts",
      "all-holdings",
    ].includes(screen) && accountId
      ? { account_id: accountId }
      : {}),
  });

  const ask = async (question: string, appendUser = true) => {
    if (requestPendingRef.current) return;
    requestPendingRef.current = true;
    const history = appendUser
      ? messages
      : messages.at(-1)?.role === "user" && messages.at(-1)?.text === question
        ? messages.slice(0, -1)
        : messages;
    const requestId = ++requestIdRef.current;
    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (appendUser) {
      setMessages((previous) => [
        ...previous,
        { id: nextId(), role: "user", text: question },
      ]);
    }
    setError(null);
    setLoading(true);
    try {
      const response = await createChatMessageApi(
        question,
        toHistory(history),
        screenContext(),
        accessToken,
        controller.signal,
      );
      if (requestIdRef.current !== requestId) return;
      setMessages((previous) => [
        ...previous,
        {
          id: response.message_id,
          role: "bot",
          text: response.text,
          status: response.status,
          caution: response.caution,
          suggestedQuestions: response.suggested_questions,
        },
      ]);
    } catch (caught) {
      if (
        requestIdRef.current !== requestId ||
        (caught instanceof DOMException && caught.name === "AbortError")
      )
        return;
      setError({
        question,
        message:
          caught instanceof ApiError
            ? caught.message
            : "물방개의 답변을 불러오지 못했어요. 잠시 후 다시 시도해주세요.",
      });
    } finally {
      if (requestIdRef.current === requestId) {
        abortControllerRef.current = null;
        requestPendingRef.current = false;
        setLoading(false);
      }
    }
  };

  const submit = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    void ask(text);
  };

  const reset = () => {
    cancelRequest();
    setMessages([]);
    setError(null);
    setLoading(false);
  };

  const close = () => {
    cancelRequest();
    setOpen(false);
  };

  const started = messages.length > 0;
  const lastMessage = messages.at(-1);
  const suggestedQuestions = lastMessage?.suggestedQuestions;
  const chips = suggestedQuestions?.length
    ? suggestedQuestions
    : QUICK_QUESTIONS;

  return (
    <>
      {open && (
        <section
          aria-label="물방개 대화창"
          aria-live="polite"
          className="fixed bottom-[104px] right-8 z-[600] flex h-[min(78vh,calc(100vh-136px))] w-[30vw] min-w-[360px] flex-col overflow-hidden rounded-[20px] bg-surface shadow-[0_20px_60px_rgba(24,36,58,0.18)]"
        >
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <div>
              <span className="text-[17px] font-bold tracking-[-0.02em]">
                물방개에게 물어보기
              </span>
              {!accessToken && (
                <p className="mt-1 text-xs text-muted">공개 금융 설명 모드</p>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                aria-label="대화 초기화"
                onClick={reset}
                className="rounded-lg p-2 text-muted hover:bg-canvas"
              >
                <RotateCcw size={17} />
              </button>
              <button
                aria-label="닫기"
                onClick={close}
                className="rounded-lg p-2 text-muted hover:bg-canvas"
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <div
            ref={scrollRef}
            className="flex flex-1 flex-col gap-3 overflow-auto px-5 py-2.5"
          >
            {!started && !loading && (
              <div className="m-auto flex w-full flex-col items-center gap-1.5">
                <div className="flex w-full flex-col items-center gap-1.5">
                  <img
                    src="/character-analyze.png"
                    alt="물방개 캐릭터"
                    className="block h-20 w-20 object-contain"
                  />
                  <span className="text-center text-base font-bold leading-6 tracking-[-0.02em]">
                    물방개에게 주식을 쉽게 물어보세요
                  </span>
                </div>
                <div className="flex w-full max-w-[280px] flex-col gap-2 pt-1.5">
                  {QUICK_QUESTIONS.map((question) => (
                    <button
                      key={question}
                      onClick={() => void ask(question)}
                      className="rounded-field bg-lime px-3.5 py-2.5 text-sm font-semibold text-[#3F5222] shadow-[0_0_0_1px_#E3EFC4_inset]"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={
                  message.role === "user"
                    ? "flex justify-end"
                    : "flex justify-start"
                }
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[15px] leading-[24px] ${
                    message.role === "user"
                      ? "bg-navy text-white"
                      : "bg-canvas text-[#3F4A43]"
                  }`}
                >
                  <p>{message.text}</p>
                  {message.role === "bot" &&
                    message.status &&
                    message.status !== "COMPLETED" && (
                      <p className="mt-2 text-xs font-semibold text-muted">
                        {message.status === "REFUSED"
                          ? "안전 정책에 따른 안내"
                          : "추가 확인이 필요한 질문"}
                      </p>
                    )}
                  {message.caution && (
                    <p className="mt-2 border-t border-line pt-2 text-xs text-muted">
                      {message.caution}
                    </p>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div
                className="my-auto flex flex-col items-center justify-center gap-2 py-5"
                role="status"
                aria-live="polite"
              >
                <img
                  src="/character-thinking.png"
                  alt="생각 중인 물방개"
                  className="h-20 w-20 object-contain"
                />
                <p className="text-sm font-semibold text-muted">
                  물방개가 답변을 준비하고 있어요
                </p>
              </div>
            )}

            {error && !loading && (
              <div className="flex flex-col items-start gap-2 rounded-2xl bg-canvas px-3.5 py-3 text-sm text-muted">
                <p>{error.message}</p>
                <button
                  onClick={() => void ask(error.question, false)}
                  className="font-semibold text-navy underline underline-offset-2"
                >
                  다시 시도
                </button>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2.5 border-t border-line px-5 pb-4 pt-3.5">
            {started && !loading && (
              <div className="flex flex-wrap gap-2">
                {chips.map((question) => (
                  <button
                    key={question}
                    onClick={() => void ask(question)}
                    className="rounded-full bg-[#F8FCEE] px-3.5 py-2.5 text-[13px] font-semibold text-[#3F5222] shadow-[0_0_0_1px_#E3EFC4_inset]"
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                aria-label="물방개 질문 입력"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && submit()}
                aria-describedby="chatbot-input-help"
                placeholder="질문을 입력하세요..."
                className="flex-1 rounded-field bg-canvas px-3.5 py-3 text-[15px] outline-none"
                disabled={loading}
                maxLength={2000}
              />
              <span id="chatbot-input-help" className="sr-only">
                Enter 키로 질문을 전송할 수 있습니다.
              </span>
              <button
                aria-label="전송"
                onClick={submit}
                className="rounded-field bg-lime p-3 text-navy disabled:opacity-40"
                disabled={!input.trim() || loading}
              >
                <ArrowUp size={18} />
              </button>
            </div>
          </div>
        </section>
      )}

      <button
        title="물방개에게 물어보기"
        onClick={() => (open ? close() : setOpen(true))}
        className="fixed bottom-8 right-8 z-[600] flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-lime shadow-[0_10px_28px_rgba(24,36,58,0.24)]"
      >
        <img
          src="/character-master.png"
          alt="물방개"
          className="h-12 w-12 object-contain"
        />
      </button>
    </>
  );
}
