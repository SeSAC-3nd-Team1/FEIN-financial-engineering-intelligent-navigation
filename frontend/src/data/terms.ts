import type { TermDef, TermKey } from '../types';

/** "?" 툴팁 내용 — 정식명 / 한글명 / 쉬운 설명 / 계산식 */
export const TERMS: Record<TermKey, TermDef> = {
  div: {
    title: '배당 수익률 (Dividend Yield)',
    ko: '(배당수익률)',
    plain: '지금 이 가격에 사면 1년 동안 배당으로 얼마를 받게 되는지를 비율로 나타낸 값이에요. 5%라면 100만원을 넣었을 때 1년에 약 5만원을 배당으로 받는다는 뜻이에요.',
    formula: '1주당 연간 배당금 ÷ 현재 주가 × 100',
  },
  pbr: {
    title: 'PBR (Price Book-value Ratio)',
    ko: '(주가순자산비율)',
    plain: '회사가 가진 순자산에 비해 주가가 몇 배인지 보는 값이에요. 1배보다 낮으면 장부에 적힌 재산보다 싸게 거래되고 있다는 뜻이에요. 다만 업종마다 기준이 달라서 같은 업종끼리 비교해야 해요.',
    formula: '주가 ÷ 1주당 순자산(BPS)',
  },
  per: {
    title: 'PER (Price Earning Ratio)',
    ko: '(주가수익비율)',
    plain: '지금 벌고 있는 이익으로 주가를 몇 년이면 회수할 수 있는지를 보는 값이에요. 낮으면 이익 대비 싸게 거래된다는 뜻이지만, 성장하는 회사는 원래 높게 거래되는 경우가 많아요.',
    formula: '주가 ÷ 1주당 순이익(EPS)',
  },
  roe: {
    title: 'ROE (Return On Equity)',
    ko: '(자기자본이익률)',
    plain: '회사가 자기 돈으로 얼마나 잘 벌었는지를 보는 값이에요. 높을수록 같은 자본으로 더 많은 이익을 냈다는 뜻이라, 꾸준히 높게 유지되는 회사를 좋게 봐요.',
    formula: '순이익 ÷ 자기자본 × 100',
  },
};
