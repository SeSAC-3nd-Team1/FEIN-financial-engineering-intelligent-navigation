import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/** 앱 전체를 감싸는 최상위 안전망 — React는 렌더링 중 예외가 나면 Error Boundary 없이는 트리 전체를
 *  언마운트해 빈 화면만 남긴다(사용자는 왜 안 되는지 알 방법이 없다). Error Boundary는 클래스
 *  컴포넌트로만 만들 수 있다(getDerivedStateFromError/componentDidCatch에 대응하는 훅이 없다).
 *  Header 등 앱의 다른 컴포넌트가 크래시 원인일 수도 있어 폴백 화면은 그걸 재사용하지 않고
 *  완전히 독립적인 마크업으로 둔다. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas px-8">
        <section role="alert" className="flex max-w-[480px] flex-col items-center gap-5 rounded-card bg-surface px-10 py-16 text-center">
          <div className="flex flex-col gap-2">
            <span className="text-[24px] font-bold">일시적인 오류가 발생했어요</span>
            <p className="text-base leading-7 text-muted">불편을 드려 죄송해요. 새로고침하면 대부분 다시 정상적으로 이용하실 수 있어요.</p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="rounded-field bg-lime px-8 py-4 text-base font-bold text-navy"
          >
            새로고침
          </button>
        </section>
      </div>
    );
  }
}
