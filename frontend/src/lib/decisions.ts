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

/** 실 계좌에 리밸런싱 판단 이력이 있으면 그 값을, 없으면(신규 계좌 등) 기존 목업을 그대로 보여준다. */
export function getDisplayDecisions(decisions: RebalancingDecisionHistoryResponse | null): DisplayDecisionSummary {
  if (decisions && decisions.items.length > 0) {
    return {
      periodLabel: decisions.period_label,
      proposed: decisions.proposed,
      accepted: decisions.accepted,
      held: decisions.held,
      items: decisions.items.map(toDisplayDecision),
    };
  }
  return {
    periodLabel: DECISION_SUMMARY.periodLabel,
    proposed: DECISION_SUMMARY.proposed,
    accepted: DECISION_SUMMARY.accepted,
    held: DECISION_SUMMARY.held,
    items: PAST_DECISIONS.map((d, i) => ({ id: `mock-${i}`, date: d.date, action: d.action, choice: d.choice, result: d.result })),
  };
}
