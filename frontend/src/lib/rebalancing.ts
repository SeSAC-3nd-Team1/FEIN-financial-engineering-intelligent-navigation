
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

/** 계좌가 없다고 "확인된" 경우(accountMissing)에만 mock(AI_ALERTS)을 쓴다. 그 외에는 실 계좌 조회
 *  결과를 그대로 보여준다 — portfolio가 있으면(제안이 0건이어도) 그 실제 결과(빈 배열)를, 아직
 *  로딩 중/조회 실패로 portfolio를 못 받았으면(portfolio === null이지만 accountMissing은 아님)
 *  빈 배열을 쓴다. portfolio === null만으로 mock을 판단하면 "계좌 없음"과 "계좌는 있는데 로딩
 *  중/조회 실패"를 구분하지 못해, 실계좌 사용자에게 지어낸 제안이 실제 제안인 것처럼 노출될 수 있다. */
export function getDisplayAlerts(portfolio: PortfolioResponse | null): AiAlert[] {
  return portfolio ? portfolio.rebalancing_proposals.map(toDisplayAlert) : [];
}
