import { AI_ALERTS } from '../data/holdings';
import type { PortfolioResponse, RebalancingProposalResponse } from './backendApi';
import { won } from './validation';
import type { AiAlert } from '../types';

/** 실 리밸런싱 제안(규칙기반, PortfolioResponse.rebalancing_proposals) 한 건을 화면 표시용 AiAlert로 바꾼다.
 *  headline/reason/action은 지금은 실 숫자만으로 조립한 사실 문장이다 — 리밸런싱 모델이 붙어 서술형 근거를
 *  주기 시작하면 이 함수 안의 문구 조립부만 그 응답으로 바꿔치면 된다(카드/모달 쪽 JSX는 그대로 둘 수 있다). */
function toDisplayAlert(p: RebalancingProposalResponse): AiAlert {
  const name = p.stock_name ?? p.stock_code;
  const current = Number(p.current_weight);
  const target = Number(p.target_weight);
  const diff = Number(p.weight_diff);
  const amount = Number(p.recommended_amount);
  const over = diff > 0;
  return {
    id: `rebalance-${p.stock_code}`,
    stockName: name,
    kind: '리밸런싱',
    badge: '리밸런싱 제안',
    headline: `목표 비중보다 ${Math.abs(diff).toFixed(1)}%p ${over ? '높아요' : '낮아요'}`,
    reason: `현재 비중 ${current.toFixed(1)}%, 목표 비중 ${target.toFixed(1)}%예요.`,
    action: `${name} 비중 ${won(Math.abs(amount))} ${over ? '축소' : '확대'} 제안`,
    currentWeight: current,
    targetWeight: target,
    recommendedAmount: amount,
  };
}

/** 실 계좌 조회가 성공했으면(portfolio가 있으면) 제안이 0건이어도 그 실제 결과(빈 배열)를 그대로
 *  보여준다 — "제안 없음"과 "계좌 자체가 없어 mock을 보여줘야 하는 상황"은 다르다. mock(AI_ALERTS)은
 *  계좌 조회 자체가 안 된 경우(비로그인·신규 계좌·조회 실패 등, portfolio === null)에만 쓴다. */
export function getDisplayAlerts(portfolio: PortfolioResponse | null): AiAlert[] {
  if (portfolio) {
    return portfolio.rebalancing_proposals.map(toDisplayAlert);
  }
  return AI_ALERTS;
}
