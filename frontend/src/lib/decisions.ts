import { DECISION_SUMMARY, PAST_DECISIONS } from '../data/holdings';
import type { RebalancingDecisionHistoryResponse } from './backendApi';

export interface DisplayDecision {
  id: string;
  date: string; // 'YYYY.MM.DD'
  action: string;
  choice: '수락' | '보류';
  /** 실 데이터일 때만 진짜 결과를 안다 — 아직 관찰 기간이 안 지났으면(actual_portfolio_return_rate가 null)
   *  지어낸 수치 대신 "아직 지켜보는 중"이라고 정직하게 보여준다. */
  result: string;
}

export interface DisplayDecisionSummary {
  periodLabel: string;
  proposed: number;
  accepted: number;
  held: number;
  items: DisplayDecision[];
}

/** 실 계좌인데 아직 이력을 못 받은 상태(로딩 중/조회 실패)에서 쓰는 기간 라벨 — mock(DECISION_SUMMARY)의
 *  값과 우연히 같지만, mock 상수에 기대지 않도록 별도로 둔다. Dashboard.tsx의 "최근 6개월 수락/보류"
 *  라벨과 동일한 관측 기간을 가리킨다. */
const DEFAULT_PERIOD_LABEL = '최근 6개월';

function toDisplayDecision(item: RebalancingDecisionHistoryResponse['items'][number]): DisplayDecision {
  const name = item.stock_name ?? item.stock_code;
  const diff = Math.abs(Number(item.weight_diff)).toFixed(1);
  const verb = item.action === 'BUY' ? '늘리기' : '줄이기';
  const returnRate = item.actual_portfolio_return_rate;
  return {
    id: item.id,
    date: item.created_at.slice(0, 10).replaceAll('-', '.'),
    action: `${name} 비중 ${diff}%p ${verb}`,
    choice: item.decision === 'ACCEPTED' ? '수락' : '보류',
    result: returnRate == null
      ? '아직 결과를 지켜보고 있어요'
      : `현재 포트폴리오 수익률 ${Number(returnRate) >= 0 ? '+' : ''}${Number(returnRate).toFixed(1)}%`,
  };
}

/** 계좌가 없다고 "확인된" 경우(accountMissing)에만 mock을 쓴다. 그 외에는 실 계좌 조회 결과를 그대로
 *  보여준다 — decisions가 있으면(판단 이력이 0건이어도) 그 실제 결과를, 아직 로딩 중/조회 실패로
 *  decisions를 못 받았으면(decisions === null이지만 accountMissing은 아님) 빈 이력을 쓴다.
 *  decisions === null만으로 mock을 판단하면 "계좌 없음"과 "계좌는 있는데 로딩 중/조회 실패"를
 *  구분하지 못해, 실계좌 사용자에게 지어낸 판단 이력이 실제 이력인 것처럼 노출될 수 있다. */
export function getDisplayDecisions(
  decisions: RebalancingDecisionHistoryResponse | null,
  accountMissing: boolean,
): DisplayDecisionSummary {
  if (accountMissing) {
    return {
      periodLabel: DECISION_SUMMARY.periodLabel,
      proposed: DECISION_SUMMARY.proposed,
      accepted: DECISION_SUMMARY.accepted,
      held: DECISION_SUMMARY.held,
      items: PAST_DECISIONS.map((d, i) => ({ id: `mock-${i}`, date: d.date, action: d.action, choice: d.choice, result: d.result })),
    };
  }
  if (!decisions) {
    return { periodLabel: DEFAULT_PERIOD_LABEL, proposed: 0, accepted: 0, held: 0, items: [] };
  }
  return {
    periodLabel: decisions.period_label,
    proposed: decisions.proposed,
    accepted: decisions.accepted,
    held: decisions.held,
    items: decisions.items.map(toDisplayDecision),
  };
}
