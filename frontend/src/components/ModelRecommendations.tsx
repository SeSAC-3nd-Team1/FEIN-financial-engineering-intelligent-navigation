import { useEffect, useState } from 'react';
import {
  getLatestModelRecommendationsApi,
  type ModelRecommendationSnapshotResponse,
} from '../lib/backendApi';

interface Props {
  token: string | null;
  limit?: number;
}

const REGIME_LABEL = { risk_on: '위험 선호', neutral: '중립', risk_off: '위험 회피' } as const;

export default function ModelRecommendations({ token, limit = 4 }: Props) {
  const [snapshot, setSnapshot] = useState<ModelRecommendationSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token) {
      setSnapshot(null);
      setFailed(false);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    getLatestModelRecommendationsApi(token)
      .then((result) => { if (!cancelled) setSnapshot(result); })
      .catch(() => { if (!cancelled) setFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="flex flex-col gap-2 rounded-[16px] bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-[#3F5222]">가격 모델 추천</span>
        {snapshot && <span className="text-[11px] text-muted">{snapshot.as_of} · {REGIME_LABEL[snapshot.market_regime]}</span>}
      </div>
      {snapshot?.source === 'fallback' && (
        <p className="text-[11px] text-down">실제 모델 결과가 없어 시연용 추천을 표시하고 있어요.</p>
      )}
      {snapshot?.source === 'generated' && snapshot.is_stale && (
        <p className="text-[11px] text-down">최근 거래일 이후 갱신되지 않은 추천이에요.</p>
      )}
      {loading ? (
        <p className="text-xs text-subtle">최신 추천을 불러오고 있어요.</p>
      ) : failed ? (
        <p className="text-xs text-down">추천을 불러오지 못했어요. 기존 포트폴리오는 유지됩니다.</p>
      ) : !token ? (
        <p className="text-xs text-subtle">로그인하면 최신 실제 편입 후보를 확인할 수 있어요.</p>
      ) : snapshot?.recommendations.length ? (
        <div className="grid grid-cols-2 gap-2">
          {snapshot.recommendations.slice(0, limit).map((item) => (
            <div key={item.symbol} className="flex min-w-0 flex-col gap-1 rounded-[10px] bg-canvas px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-semibold text-ink">{item.stock_name ?? item.symbol}</span>
                <span className="shrink-0 text-[11px] font-bold text-[#3F5222]">{(item.target_weight * 100).toFixed(0)}%</span>
              </div>
              <span className="truncate text-[11px] text-muted">{item.rank}위 · {item.reason}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-subtle">현재 표시할 모델 추천이 없어요.</p>
      )}
      {snapshot && (
        <span className="self-end text-[10px] text-subtle">
          {snapshot.model_version} · {snapshot.source === 'generated' ? '실제 모델' : '샘플'} · 가상투자 참고용
        </span>
      )}
    </div>
  );
}
