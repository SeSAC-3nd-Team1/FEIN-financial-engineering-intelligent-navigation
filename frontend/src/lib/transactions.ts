import { ALL_HOLDINGS, RECENT_TRANSACTIONS, STOCK_INFO } from '../data/holdings';
import type { ExecutionResponse } from './backendApi';
import type { TransactionRecord } from '../types';

/** 실 계좌의 체결 내역(ExecutionResponse)을 거래 내역 화면이 쓰는 표시 모델로 변환한다.
 *  실 체결에는 종목명(코드만 있음)·수수료·리밸런싱/배당 구분이 없어, 있는 정보만 최대한 채운다. */
function toDisplayTransaction(execution: ExecutionResponse): TransactionRecord {
  const holding = ALL_HOLDINGS.find((h) => STOCK_INFO[h.name]?.code === execution.stock_code);
  const stockName = holding?.name ?? execution.stock_code;
  const price = Number(execution.execution_price);
  const quantity = Number(execution.quantity);
  const amount = execution.side === 'BUY' ? price * quantity : -(price * quantity);

  return {
    id: String(execution.id),
    date: execution.executed_at.slice(0, 10).replace(/-/g, '.'),
    type: execution.side === 'BUY' ? '매수' : '매도',
    stockName,
    amount,
    note: `${quantity}주 체결`,
    quantity,
    price,
    fee: 0,
    status: '체결완료',
  };
}

/** 거래 내역 목록 — 실 계좌가 있으면 체결 기록을 최신순으로 그대로 쓴다(0건이어도 실제 빈 상태).
 *  실 계좌 자체가 없을 때(hasAccount=false)만 목업으로 대체한다 — "계좌 없음"과 "계좌는 있는데
 *  체결이 0건"은 다른 상태라, executions.length만으로 판단하면 신규 계좌의 진짜 빈 내역이
 *  목업으로 가려진다. */
export function getDisplayTransactions(executions: ExecutionResponse[], hasAccount: boolean): TransactionRecord[] {
  if (!hasAccount) return RECENT_TRANSACTIONS;
  return [...executions]
    .sort((a, b) => b.executed_at.localeCompare(a.executed_at))
    .map(toDisplayTransaction);
}
