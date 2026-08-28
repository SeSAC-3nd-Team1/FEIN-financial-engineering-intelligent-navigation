import type { ReactNode } from 'react';
import type { Screen } from '../types';

interface Props {
  userName: string;
  onNavigate: (screen: Screen) => void;
  loading: boolean;
  accountMissing: boolean;
  error: unknown;
  onRetry: () => void;
  children: ReactNode;
}

export default function PortfolioDataState({
  userName,
  onNavigate,
  loading,
  accountMissing,
  error,
  onRetry,
  children,
}: Props) {
  if (!loading && !accountMissing && !error) return <>{children}</>;

  const title = loading
    ? '포트폴리오를 불러오는 중이에요'
    : accountMissing
      ? '투자 계좌를 준비해주세요'
      : '포트폴리오를 불러오지 못했어요';
  const message = loading
    ? '잠시만 기다려주세요.'
    : accountMissing
      ? '계좌를 준비하면 보유 종목과 투자 현황을 확인할 수 있어요.'
      : '네트워크 상태를 확인한 뒤 다시 시도해주세요.';

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-20 items-center justify-between border-b border-line px-16">
        <button onClick={() => onNavigate('home')} className="text-xl font-bold text-navy">FE!N</button>
        <span className="text-sm text-muted">{userName}</span>
      </header>
      <main className="flex min-h-[520px] flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-2xl font-bold text-ink">{title}</h1>
        <p className="text-base text-subtle">{message}</p>
        {accountMissing ? (
          <button onClick={() => onNavigate('strategy-list')} className="rounded-field bg-navy px-6 py-3 font-bold text-white">
            계좌 준비하기
          </button>
        ) : !loading && (
          <button onClick={onRetry} className="rounded-field bg-navy px-6 py-3 font-bold text-white">
            다시 시도
          </button>
        )}
      </main>
    </div>
  );
}
