import type { AiAlert, Holding, StockInfo, TransactionRecord } from '../types';

export const HOLD_TOTAL = 1_083_400;

/** AI 평가 5축 — Portfolio "위험 분석" 탭 레이더의 꼭짓점 순서와 동일 */
export const AI_AXES = ['안정성', '재무 건전성', '성장성', '방어력', '분산 기여'] as const;

/** AI 평가 6축 — StockDetail "AI 평가" 레이더/막대의 꼭짓점 순서와 동일 (요구사항 고정 라벨) */
export const AI_EVAL_AXES = ['PER', 'PBR', 'ROE', '배당수익률', '성장성', '안정성'] as const;

export const ALL_HOLDINGS: Holding[] = [
  { name: '삼성전자', sector: '반도체', pct: 18.0, chg: 1.2, principal: 179_899, returnRate: 8.4, why: '변동성이 낮고 재무가 안정적이라 포트폴리오의 중심을 잡아줘요.' },
  { name: 'SK하이닉스', sector: '반도체', pct: 16.2, target: 14, chg: 2.4, principal: 143_157, returnRate: 22.6, why: '최근 많이 올라 목표 14%보다 비중이 커졌어요. 리밸런싱 후보예요.' },
  { name: 'KT&G', sector: '필수소비재', pct: 11.0, chg: -0.4, principal: 113_280, returnRate: 5.2, why: '경기와 무관하게 수요가 꾸준해 하락장에서 방어 역할을 해요.' },
  { name: 'NAVER', sector: '인터넷', pct: 9.0, chg: 0.8, principal: 100_626, returnRate: -3.1, why: '제조업과 다른 시점에 움직여 분산 효과를 만들어요.' },
  { name: '현대차', sector: '자동차', pct: 6.4, chg: 1.6, principal: 62_244, returnRate: 11.4, why: '배당이 꾸준하고 밸류에이션 부담이 낮은 편이에요.' },
  { name: '셀트리온', sector: '바이오', pct: 4.8, chg: -1.1, principal: 55_798, returnRate: -6.8, why: '의약품 수요는 경기와 무관해 다른 업종과 함께 담기 좋아요.' },
  { name: '기아', sector: '자동차', pct: 4.2, chg: 1.4, principal: 39_846, returnRate: 14.2, why: '현대차와 판매 지역이 달라 같은 업종 안에서도 분산이 돼요.' },
  { name: 'LG생활건강', sector: '필수소비재', pct: 3.6, chg: -0.6, principal: 43_057, returnRate: -9.4, why: '생필품 수요가 안정적이라 변동성을 낮춰줘요.' },
  { name: 'POSCO홀딩스', sector: '철강', pct: 3.2, chg: 0.5, principal: 33_791, returnRate: 2.6, why: '소비재와 다른 시점에 좋아져 경기 사이클을 나눠 담아요.' },
  { name: '삼성바이오로직스', sector: '바이오', pct: 2.9, chg: -0.3, principal: 32_900, returnRate: -4.5, why: '장기 계약 기반이라 매출 예측이 비교적 쉬운 편이에요.' },
  { name: 'KB금융', sector: '금융', pct: 2.6, chg: 0.9, principal: 23_690, returnRate: 18.9, why: '배당이 높아 전체 수익의 바닥을 받쳐줘요.' },
  { name: '신한지주', sector: '금융', pct: 2.4, chg: 0.7, principal: 22_357, returnRate: 16.3, why: 'KB금융과 대출 구성이 달라 금융 업종 안에서 나눠 담았어요.' },
  { name: '하나금융지주', sector: '금융', pct: 2.1, chg: 0.6, principal: 18_991, returnRate: 19.8, why: '외환·기업금융 비중이 높아 금리 국면에서 다르게 움직여요.' },
  { name: '삼성화재', sector: '금융', pct: 1.9, chg: 0.4, principal: 18_265, returnRate: 12.7, why: '보험 특유의 현금 흐름 덕에 하락장에서 잘 견뎌요.' },
  { name: 'LG전자', sector: '전자', pct: 1.8, chg: 1.0, principal: 18_381, returnRate: 6.1, why: '가전 수요가 꾸준해 반도체 중심 종목과 균형을 맞춰줘요.' },
  { name: '카카오', sector: '인터넷', pct: 1.6, chg: -2.1, principal: 24_209, returnRate: -28.4, why: '변동성이 커서 비중을 작게 유지했어요.' },
  { name: '한국전력', sector: '유틸리티', pct: 1.5, chg: -0.2, principal: 15_656, returnRate: 3.8, why: '전기 수요는 경기와 무관해 방어 역할을 해요.' },
  { name: 'SK텔레콤', sector: '통신', pct: 1.4, chg: 0.3, principal: 13_839, returnRate: 9.6, why: '매달 들어오는 요금 매출과 높은 배당이 안정성을 더해요.' },
  { name: '유한양행', sector: '제약', pct: 1.3, chg: -0.5, principal: 15_177, returnRate: -7.2, why: '기본 사업이 꾸준해 바이오 변동성을 완화해줘요.' },
  { name: '오리온', sector: '필수소비재', pct: 1.1, chg: 0.2, principal: 10_784, returnRate: 10.5, why: '해외 매출 비중이 커서 국내 소비 종목과 다르게 움직여요.' },
];

export const STOCK_INFO: Record<string, StockInfo> = {
  '삼성전자': { code: '005930', price: 78400, cap: '468조원', div: '2.1%', pbr: '1.4배', per: '13.2배', roe: '10.8%', ai: [82, 88, 74, 70, 91],
    aiEval: [60, 65, 55, 40, 74, 82], finance: { debtRatio: 27, currentRatio: 218, quickRatio: 178, interestCoverage: 145 },
    desc: '메모리 반도체와 스마트폰, 가전을 함께 만드는 회사예요. 매출의 큰 축은 D램·낸드 같은 메모리 반도체이고, 여기에 갤럭시 스마트폰과 TV·생활가전이 더해져요. 반도체 가격이 오르내릴 때 실적이 함께 움직이지만, 사업이 여러 갈래로 나뉘어 있어 한쪽이 부진해도 전체가 크게 흔들리진 않는 편이에요.' },
  'SK하이닉스': { code: '000660', price: 214500, cap: '156조원', div: '0.6%', pbr: '2.1배', per: '11.4배', roe: '18.6%', ai: [74, 62, 92, 58, 84],
    aiEval: [65, 45, 85, 15, 92, 74], finance: { debtRatio: 38, currentRatio: 172, quickRatio: 138, interestCoverage: 42 },
    desc: 'D램과 낸드플래시를 만드는 메모리 반도체 전문 회사예요. AI 서버에 쓰이는 고대역폭 메모리(HBM)에서 앞서 있어 최근 실적이 빠르게 좋아졌어요. 사업이 메모리 한 축에 집중돼 있어서 반도체 경기에 따라 실적과 주가가 크게 움직이는 편이에요.' },
  'KT&G': { code: '033780', price: 91200, cap: '11조원', div: '5.4%', pbr: '1.2배', per: '10.8배', roe: '11.2%', ai: [88, 94, 46, 92, 72],
    aiEval: [68, 70, 57, 85, 46, 88], finance: { debtRatio: 32, currentRatio: 195, quickRatio: 168, interestCoverage: 68 },
    desc: '담배와 건강기능식품(정관장)을 만드는 회사예요. 수요가 경기와 크게 무관해서 매출이 급격히 줄어드는 일이 드물고, 그만큼 배당을 꾸준히 주는 편이에요. 성장 속도는 빠르지 않지만 시장이 흔들릴 때 덜 떨어지는 역할을 합니다.' },
  'NAVER': { code: '035420', price: 186500, cap: '30조원', div: '0.4%', pbr: '1.1배', per: '18.6배', roe: '6.4%', ai: [70, 68, 78, 60, 76],
    aiEval: [40, 72, 35, 10, 78, 70], finance: { debtRatio: 41, currentRatio: 152, quickRatio: 140, interestCoverage: 55 },
    desc: '검색 포털과 커머스, 웹툰, 클라우드를 운영하는 인터넷 회사예요. 광고와 커머스 수수료가 주 수입원이고, 최근에는 AI와 클라우드 사업을 키우고 있어요. 제조업과 실적이 움직이는 시점이 달라 포트폴리오 안에서 분산 역할을 합니다.' },
  '현대차': { code: '005380', price: 241000, cap: '51조원', div: '4.2%', pbr: '0.6배', per: '5.4배', roe: '12.4%', ai: [76, 74, 68, 72, 80],
    aiEval: [90, 92, 60, 70, 68, 76], finance: { debtRatio: 118, currentRatio: 108, quickRatio: 92, interestCoverage: 22 },
    desc: '자동차를 만들어 세계 시장에 파는 회사예요. 최근에는 전기차와 하이브리드 비중을 빠르게 늘리고 있어요. 매출의 대부분이 해외에서 나와서 환율과 해외 경기의 영향을 함께 받습니다.' },
  '셀트리온': { code: '068270', price: 178300, cap: '38조원', div: '0.3%', pbr: '2.4배', per: '32.1배', roe: '7.8%', ai: [62, 58, 74, 66, 70],
    aiEval: [15, 38, 40, 8, 74, 62], finance: { debtRatio: 22, currentRatio: 285, quickRatio: 260, interestCoverage: 38 },
    desc: '오리지널 바이오 의약품을 대체하는 바이오시밀러를 개발·판매하는 회사예요. 의약품 수요는 경기와 크게 관계없이 이어지는 편이라, 경기 민감 업종과 다른 흐름을 만들어요.' },
  '기아': { code: '000270', price: 112800, cap: '45조원', div: '4.8%', pbr: '0.7배', per: '4.8배', roe: '15.2%', ai: [78, 76, 70, 74, 78],
    aiEval: [92, 90, 72, 78, 70, 78], finance: { debtRatio: 95, currentRatio: 132, quickRatio: 108, interestCoverage: 28 },
    desc: '현대차그룹의 자동차 회사로, SUV와 전기차 라인업이 강한 편이에요. 같은 자동차 산업이지만 판매 지역과 차종 구성이 달라 현대차와 함께 담아도 분산 효과가 있어요.' },
  'LG생활건강': { code: '051900', price: 342000, cap: '5조원', div: '1.8%', pbr: '0.8배', per: '16.4배', roe: '5.2%', ai: [80, 72, 52, 84, 66],
    aiEval: [48, 85, 28, 35, 52, 80], finance: { debtRatio: 34, currentRatio: 148, quickRatio: 112, interestCoverage: 34 },
    desc: '생활용품과 화장품, 음료를 만드는 회사예요. 생필품 수요가 꾸준해 매출 변동이 작은 편이고, 화장품은 중국 등 해외 소비 흐름에 영향을 받습니다.' },
  'POSCO홀딩스': { code: '005490', price: 289500, cap: '24조원', div: '3.6%', pbr: '0.5배', per: '12.8배', roe: '4.6%', ai: [68, 70, 62, 64, 74],
    aiEval: [62, 95, 24, 62, 62, 68], finance: { debtRatio: 68, currentRatio: 128, quickRatio: 92, interestCoverage: 12 },
    desc: '철강을 만드는 회사이자 이차전지 소재 사업을 키우고 있는 지주회사예요. 건설·자동차 등 산업 경기에 따라 실적이 움직여서, 소비재 종목과는 다른 시점에 좋아지고 나빠집니다.' },
  '삼성바이오로직스': { code: '207940', price: 812000, cap: '58조원', div: '0.0%', pbr: '3.8배', per: '48.2배', roe: '9.4%', ai: [64, 60, 86, 70, 68],
    aiEval: [5, 10, 48, 5, 86, 64], finance: { debtRatio: 45, currentRatio: 310, quickRatio: 275, interestCoverage: 24 },
    desc: '다른 제약사의 의약품을 대신 만들어주는 위탁생산(CMO) 회사예요. 장기 계약이 많아 매출이 비교적 예측 가능하지만, 성장 기대가 주가에 미리 반영돼 있는 편이에요.' },
  'KB금융': { code: '105560', price: 84600, cap: '33조원', div: '4.6%', pbr: '0.5배', per: '5.8배', roe: '9.2%', ai: [82, 84, 54, 78, 76],
    aiEval: [88, 95, 48, 75, 54, 82], finance: { debtRatio: 892, currentRatio: 118, quickRatio: 105, interestCoverage: 2.1 },
    desc: '은행을 중심으로 증권·보험을 함께 운영하는 금융지주회사예요. 대출 이자에서 나오는 수익이 크고, 배당을 꾸준히 주는 편이라 전체 수익의 바닥을 받쳐줍니다.' },
  '신한지주': { code: '055550', price: 52400, cap: '27조원', div: '4.4%', pbr: '0.5배', per: '5.6배', roe: '8.8%', ai: [80, 82, 54, 78, 74],
    aiEval: [89, 95, 46, 72, 54, 80], finance: { debtRatio: 875, currentRatio: 115, quickRatio: 102, interestCoverage: 2.0 },
    desc: '신한은행을 중심으로 한 금융지주회사예요. KB금융과 사업 구조가 비슷하지만 대출 구성과 해외 사업 비중이 달라, 금융 업종 안에서 나눠 담는 의미가 있어요.' },
  '하나금융지주': { code: '086790', price: 61800, cap: '18조원', div: '5.1%', pbr: '0.4배', per: '5.2배', roe: '8.4%', ai: [78, 80, 52, 80, 72],
    aiEval: [91, 97, 44, 80, 52, 78], finance: { debtRatio: 910, currentRatio: 112, quickRatio: 98, interestCoverage: 1.9 },
    desc: '하나은행을 중심으로 한 금융지주회사예요. 기업 금융과 외환 사업 비중이 상대적으로 높아 금리와 환율 흐름에 따라 실적이 달라집니다.' },
  '삼성화재': { code: '000810', price: 348000, cap: '16조원', div: '4.0%', pbr: '0.8배', per: '8.4배', roe: '10.2%', ai: [84, 86, 50, 82, 78],
    aiEval: [78, 85, 54, 66, 50, 84], finance: { debtRatio: 268, currentRatio: 142, quickRatio: 128, interestCoverage: 8.4 },
    desc: '자동차·건강 보험을 판매하는 손해보험 회사예요. 보험료를 미리 받고 나중에 보험금을 주는 구조라, 시장이 하락할 때도 상대적으로 견디는 편이에요.' },
  'LG전자': { code: '066570', price: 98700, cap: '16조원', div: '1.6%', pbr: '0.8배', per: '9.6배', roe: '8.6%', ai: [74, 72, 64, 70, 76],
    aiEval: [72, 85, 45, 30, 64, 74], finance: { debtRatio: 128, currentRatio: 118, quickRatio: 88, interestCoverage: 15 },
    desc: 'TV와 생활가전, 전장(자동차 부품) 사업을 하는 회사예요. 가전은 수요가 꾸준하고 전장은 성장하는 축이어서, 반도체 중심 종목과 다른 흐름을 만듭니다.' },
  '카카오': { code: '035720', price: 42150, cap: '19조원', div: '0.2%', pbr: '1.3배', per: '38.4배', roe: '2.8%', ai: [54, 52, 72, 48, 62],
    aiEval: [10, 68, 15, 5, 72, 54], finance: { debtRatio: 58, currentRatio: 138, quickRatio: 122, interestCoverage: 4.2 },
    desc: '메신저를 기반으로 커머스·금융·콘텐츠 사업을 하는 인터넷 회사예요. 신규 사업 투자가 많아 이익 변동이 크고 주가도 많이 움직이는 편이라, 비중을 작게 유지했어요.' },
  '한국전력': { code: '015760', price: 22350, cap: '14조원', div: '0.0%', pbr: '0.4배', per: '6.2배', roe: '3.4%', ai: [66, 74, 44, 88, 58],
    aiEval: [86, 97, 18, 5, 44, 66], finance: { debtRatio: 210, currentRatio: 68, quickRatio: 52, interestCoverage: 0.8 },
    desc: '전기를 생산·공급하는 공기업이에요. 전기 수요는 경기와 거의 무관해서 매출이 안정적이지만, 연료 가격과 요금 정책에 따라 이익이 크게 달라집니다.' },
  'SK텔레콤': { code: '017670', price: 58900, cap: '13조원', div: '6.2%', pbr: '1.0배', per: '10.2배', roe: '9.8%', ai: [82, 88, 46, 90, 70],
    aiEval: [70, 75, 50, 95, 46, 82], finance: { debtRatio: 132, currentRatio: 98, quickRatio: 88, interestCoverage: 18 },
    desc: '이동통신 서비스를 제공하는 회사예요. 매달 들어오는 요금이 매출의 기반이라 실적이 안정적이고, 배당 수익률이 높은 편이에요.' },
  '유한양행': { code: '000100', price: 118400, cap: '9조원', div: '0.6%', pbr: '2.2배', per: '34.6배', roe: '4.2%', ai: [66, 64, 70, 72, 66],
    aiEval: [13, 42, 22, 15, 70, 66], finance: { debtRatio: 24, currentRatio: 245, quickRatio: 205, interestCoverage: 62 },
    desc: '의약품과 생활건강 제품을 만드는 제약 회사예요. 신약 기술수출 성과에 따라 기대가 달라지지만, 기본 사업은 꾸준한 편이에요.' },
  '오리온': { code: '271560', price: 132500, cap: '5조원', div: '1.2%', pbr: '1.1배', per: '11.8배', roe: '10.4%', ai: [78, 80, 58, 82, 72],
    aiEval: [65, 72, 55, 22, 58, 78], finance: { debtRatio: 42, currentRatio: 168, quickRatio: 132, interestCoverage: 45 },
    desc: '과자와 스낵을 만드는 식품 회사예요. 중국·베트남 등 해외 매출 비중이 커서 국내 소비만 보는 종목과는 다른 흐름을 만듭니다.' },
};

/* ----- Portfolio "내 포트폴리오 자세히 보기" (Power BI 스타일 분석 섹션) ----- */

export interface TrendPoint { label: string; port: number; kospi: number; }

/** 자산 변화 — 내 포트폴리오 vs KOSPI 누적 수익률(%), 지난해 10월 ~ 오늘 */
export const PORTFOLIO_TREND: TrendPoint[] = [
  { label: '지난해 10월', port: 0, kospi: 0 },
  { label: '지난해 11월', port: 1.4, kospi: -1.8 },
  { label: '지난해 12월', port: 2.1, kospi: -3.2 },
  { label: '올해 1월', port: 1.2, kospi: -4.6 },
  { label: '올해 2월', port: 3.6, kospi: -1.4 },
  { label: '올해 3월', port: 4.8, kospi: 0.6 },
  { label: '올해 4월', port: 4.1, kospi: -0.9 },
  { label: '올해 5월', port: 5.9, kospi: 1.8 },
  { label: '올해 6월', port: 3.2, kospi: -6.8 },
  { label: '올해 7월', port: 6.4, kospi: 2.4 },
  { label: '올해 8월', port: 8.34, kospi: 3.1 },
  { label: '오늘', port: 8.34, kospi: 3.1 },
];

export interface ContributionItem { name: string; amount: number; }

/** 종목별 기여 — 최근 1개월 동안 각 종목이 전체 수익에 기여한 금액 */
export const STOCK_CONTRIBUTION: ContributionItem[] = [
  { name: '삼성전자', amount: 12_400 },
  { name: 'SK하이닉스', amount: 8_100 },
  { name: 'NAVER', amount: 4_200 },
  { name: 'KT&G', amount: 2_600 },
  { name: 'POSCO홀딩스', amount: -1_900 },
];

export interface DecisionRecord { date: string; action: string; choice: '수락' | '보류'; result: string; }

/** 최근 판단 기록 — AI 리밸런싱 제안에 대한 사용자 결정과 그 결과 */
export const PAST_DECISIONS: DecisionRecord[] = [
  { date: '2026.07.15', action: '삼성전자 비중 3% 줄이기', choice: '수락', result: '현재 자산 +12,400원' },
  { date: '2026.06.28', action: 'SK하이닉스 비중 2% 늘리기', choice: '보류', result: '이후 2주간 변동성 소폭 상승' },
  { date: '2026.06.12', action: 'KT&G 비중 1% 늘리기', choice: '수락', result: '변동성 방어 효과 확인' },
  { date: '2026.05.30', action: '현금 비중 5% 줄이기', choice: '보류', result: '이후 수익률은 유지' },
];

/** 최근 6개월 판단 요약 통계 + AI 제안을 따랐을 때 vs 실제 선택의 평균 변동성 비교 */
export const DECISION_SUMMARY = {
  periodLabel: '최근 6개월',
  proposed: 8,
  accepted: 5,
  held: 3,
  volIfFollowed: 10.8,
  volActual: 12.1,
};

/** AI 손절/리밸런싱 제안 — 백엔드에 판단 로직이 아직 없어 목업 데이터다.
 *  Portfolio "AI 제안" 카드 + 보유 종목 배지 + "왜 지금인가요?" 모달이 이 배열을 공유한다. */
export const AI_ALERTS: AiAlert[] = [
  {
    id: 'alert-skhynix-rebalance',
    stockName: 'SK하이닉스',
    kind: '리밸런싱',
    badge: '리밸런싱 제안',
    headline: '목표 비중보다 2.2%p 초과 편입됐어요',
    reason: '최근 급등으로 SK하이닉스 비중이 목표 14%를 넘어 16.2%까지 올라왔어요. 반도체 업종 하나에 집중도가 높아지면 포트폴리오 전체의 분산 효과가 줄어들 수 있어요.',
    action: 'SK하이닉스 비중 2%p 축소 제안',
  },
  {
    id: 'alert-kakao-losscut',
    stockName: '카카오',
    kind: '손절',
    badge: '손절 검토',
    headline: '3개 분기 연속 영업이익이 줄었어요',
    reason: '카카오는 최근 3개 분기 연속 영업이익이 감소했고, 최근 한 달 변동성도 시장 평균보다 높게 유지되고 있어요. 반등 신호가 뚜렷해지기 전까지는 비중을 낮추는 것을 권해요.',
    action: '비중 축소 또는 전량 매도 검토',
  },
  {
    id: 'alert-samsung-rebalance',
    stockName: '삼성전자',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '목표 비중 대비 완만하게 늘었어요',
    reason: '최근 꾸준한 상승으로 삼성전자 비중이 소폭 늘었어요. 아직 위험한 수준은 아니지만 상승세가 이어지면 비중 조정이 필요할 수 있어요.',
    action: '지금은 유지, 20%를 넘으면 축소 검토',
  },
  {
    id: 'alert-ktng-review',
    stockName: 'KT&G',
    kind: '손절',
    badge: '실적 점검',
    headline: '등락률이 최근 계속 약세예요',
    reason: 'KT&G는 최근 등락률이 약세를 보이고 있어요. 다만 배당 수익률이 높고 방어주 성격이 강해 손절보다는 관찰이 먼저예요.',
    action: '비중 유지, 2주간 추가 하락 시 재검토',
  },
  {
    id: 'alert-naver-rebalance',
    stockName: 'NAVER',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '목표 비중에 가까워지고 있어요',
    reason: 'AI·클라우드 사업 기대감으로 NAVER 비중이 서서히 늘고 있어요. 인터넷 업종 집중도가 높아지지 않도록 지켜볼 필요가 있어요.',
    action: '비중 유지, 추가 상승 시 일부 차익 실현 검토',
  },
  {
    id: 'alert-hyundai-rebalance',
    stockName: '현대차',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '수익률이 좋아 비중이 커지고 있어요',
    reason: '현대차는 최근 수익률이 좋아 비중이 자연스럽게 늘었어요. 자동차 업종(기아 포함) 비중이 너무 커지지 않게 확인이 필요해요.',
    action: '기아와 합산 비중이 15%를 넘으면 조정 검토',
  },
  {
    id: 'alert-celltrion-review',
    stockName: '셀트리온',
    kind: '손절',
    badge: '손절 검토',
    headline: '바이오 업종 변동성이 커지고 있어요',
    reason: '셀트리온은 최근 등락률이 약세이고 바이오 업종 전반의 변동성도 커졌어요. 실적 발표 전까지 비중을 유지할지 점검이 필요해요.',
    action: '실적 발표 확인 후 비중 유지 여부 결정',
  },
  {
    id: 'alert-kia-rebalance',
    stockName: '기아',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '현대차와 합산 비중이 늘고 있어요',
    reason: '기아 역시 수익률이 좋아 비중이 커졌어요. 같은 자동차 업종인 현대차와 합치면 자동차 업종 집중도가 높아지고 있어요.',
    action: '자동차 업종 합산 비중을 주기적으로 확인',
  },
  {
    id: 'alert-lghnh-review',
    stockName: 'LG생활건강',
    kind: '손절',
    badge: '손절 검토',
    headline: '화장품 수요 둔화로 약세가 이어져요',
    reason: '중국向 화장품 수요 둔화로 LG생활건강 주가가 약세를 이어가고 있어요. 반등 신호가 보이기 전까지는 비중을 늘리지 않는 게 좋아요.',
    action: '추가 매수 보류, 반등 신호 확인 후 재검토',
  },
  {
    id: 'alert-posco-rebalance',
    stockName: 'POSCO홀딩스',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '이차전지 소재 기대감에 비중이 늘었어요',
    reason: '이차전지 소재 사업 기대감으로 POSCO홀딩스 비중이 서서히 늘고 있어요. 철강 업황에 따라 다시 조정될 수 있어요.',
    action: '비중 유지, 철강 업황 지표 계속 확인',
  },
  {
    id: 'alert-samsungbio-review',
    stockName: '삼성바이오로직스',
    kind: '손절',
    badge: '실적 점검',
    headline: '고평가 우려로 등락률이 약세예요',
    reason: '삼성바이오로직스는 밸류에이션 부담으로 최근 등락률이 약세예요. 장기 계약 기반이라 매출 자체는 안정적이니 손절보다는 관찰이 먼저예요.',
    action: '비중 유지, PER 추이 계속 확인',
  },
  {
    id: 'alert-kbfinance-rebalance',
    stockName: 'KB금융',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '금융주 강세로 비중이 늘고 있어요',
    reason: '고배당 매력으로 KB금융 비중이 꾸준히 늘고 있어요. 신한·하나 등 다른 금융주와 합치면 금융 업종 집중도가 높아질 수 있어요.',
    action: '금융 업종 합산 비중이 20%를 넘으면 조정 검토',
  },
  {
    id: 'alert-shinhan-rebalance',
    stockName: '신한지주',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '금융 업종 비중이 함께 늘고 있어요',
    reason: 'KB금융과 마찬가지로 신한지주도 배당 매력에 비중이 늘었어요. 금융 업종 전체 비중을 함께 확인할 필요가 있어요.',
    action: 'KB금융과 합산 비중 확인',
  },
  {
    id: 'alert-hanafinance-rebalance',
    stockName: '하나금융지주',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '금리 상승 기대에 비중이 늘었어요',
    reason: '금리 상승 기대감으로 하나금융지주 비중이 늘었어요. 다른 금융주와 함께 업종 집중도를 확인해야 해요.',
    action: '금융 업종 합산 비중 확인',
  },
  {
    id: 'alert-samsungfire-rebalance',
    stockName: '삼성화재',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '방어주 매력에 비중이 늘고 있어요',
    reason: '시장 변동성이 커지며 방어적인 보험주 삼성화재 비중이 자연스럽게 늘었어요. 큰 위험은 아니지만 추이를 지켜볼 필요가 있어요.',
    action: '비중 유지, 큰 변화 없으면 관찰만',
  },
  {
    id: 'alert-lge-rebalance',
    stockName: 'LG전자',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '가전·전장 실적 개선으로 비중이 늘었어요',
    reason: '전장(자동차 부품) 사업 성장으로 LG전자 비중이 늘고 있어요. 반도체 중심 종목과 균형을 맞추는 역할을 하는지 계속 확인이 필요해요.',
    action: '비중 유지, 전장 사업 실적 계속 확인',
  },
  {
    id: 'alert-kepco-review',
    stockName: '한국전력',
    kind: '손절',
    badge: '실적 점검',
    headline: '연료 가격 부담으로 약세가 이어져요',
    reason: '연료 가격 부담으로 한국전력 실적이 약세를 이어가고 있어요. 전기 요금 정책 변화가 있을 때까지는 비중을 늘리지 않는 게 좋아요.',
    action: '추가 매수 보류, 요금 정책 발표 확인',
  },
  {
    id: 'alert-sktelecom-rebalance',
    stockName: 'SK텔레콤',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '높은 배당으로 비중이 조금씩 늘어요',
    reason: '높은 배당 수익률 덕분에 SK텔레콤 비중이 서서히 늘고 있어요. 통신 업종 특성상 큰 변동은 없지만 주기적으로 확인이 필요해요.',
    action: '비중 유지, 배당 재투자 시 비중 재확인',
  },
  {
    id: 'alert-yuhan-review',
    stockName: '유한양행',
    kind: '손절',
    badge: '손절 검토',
    headline: '신약 기술수출 기대가 약해졌어요',
    reason: '신약 기술수출 관련 기대감이 낮아지며 유한양행 등락률이 약세예요. 기본 사업은 꾸준하니 급하게 손절하기보다는 관찰이 먼저예요.',
    action: '비중 유지, 기술수출 뉴스 계속 확인',
  },
  {
    id: 'alert-orion-rebalance',
    stockName: '오리온',
    kind: '리밸런싱',
    badge: '비중 점검',
    headline: '해외 매출 호조로 비중이 늘고 있어요',
    reason: '중국·베트남 매출이 늘며 오리온 비중이 서서히 커지고 있어요. 국내 소비 종목과 다른 흐름이라 분산 효과는 유지되고 있어요.',
    action: '비중 유지, 해외 매출 비중 계속 확인',
  },
];

/** "AI 알고리즘 vs 내 포트폴리오" 비교 카드 — 백엔드에 자동매매 비교 지표가 없어 목업이다.
 *  myReturn 은 PORTFOLIO_TREND 오늘 값과 동일하게 맞춰뒀다. */
export const AUTO_VS_MANUAL = {
  periodLabel: '최근 6개월',
  aiReturn: 11.4,
  myReturn: 8.34,
  aiVol: 9.8,
  myVol: 12.1,
};

/** 최근 거래 내역 — 실 계좌의 체결 내역(executions)이 있으면 그걸 우선 쓰고, 없을 때만 이 목업을 보여준다.
 *  소수점 투자 기준이라 quantity 는 소수 주 단위이고, price 는 체결 시점 단가(현재가로 근사)다. */
export const RECENT_TRANSACTIONS: TransactionRecord[] = [
  { id: 'tx-1', date: '2026.08.20', type: '매수', stockName: '삼성전자', amount: 50_000, note: '정기 적립 매수', quantity: 0.638, price: 78_400, fee: 8, status: '체결완료' },
  { id: 'tx-2', date: '2026.08.18', type: '리밸런싱', stockName: 'SK하이닉스', amount: -21_600, note: 'AI 리밸런싱 제안 수락 — 비중 축소', quantity: 0.101, price: 214_500, fee: 3, status: '체결완료' },
  { id: 'tx-3', date: '2026.08.15', type: '매도', stockName: '카카오', amount: -17_300, note: 'AI 손절 제안 수락', quantity: 0.410, price: 42_150, fee: 3, status: '체결완료' },
  { id: 'tx-4', date: '2026.08.10', type: '매수', stockName: 'KT&G', amount: 30_000, note: '정기 적립 매수', quantity: 0.329, price: 91_200, fee: 5, status: '체결완료' },
  { id: 'tx-5', date: '2026.08.05', type: '배당', stockName: 'SK텔레콤', amount: 940, note: '분기 배당금 입금', quantity: 0, price: 0, fee: 0, status: '체결완료' },
  { id: 'tx-6', date: '2026.07.28', type: '매수', stockName: '현대차', amount: 40_000, note: '정기 적립 매수', quantity: 0.166, price: 241_000, fee: 6, status: '체결완료' },
  { id: 'tx-7', date: '2026.07.24', type: '매수', stockName: 'NAVER', amount: 35_000, note: '정기 적립 매수', quantity: 0.188, price: 186_500, fee: 5, status: '체결완료' },
  { id: 'tx-8', date: '2026.07.20', type: '매도', stockName: '셀트리온', amount: -15_000, note: 'AI 손절 제안 검토 후 일부 매도', quantity: 0.084, price: 178_300, fee: 3, status: '체결완료' },
  { id: 'tx-9', date: '2026.07.16', type: '매수', stockName: '기아', amount: 25_000, note: '정기 적립 매수', quantity: 0.222, price: 112_800, fee: 4, status: '체결완료' },
  { id: 'tx-10', date: '2026.07.12', type: '리밸런싱', stockName: 'LG생활건강', amount: -18_000, note: 'AI 리밸런싱 제안 수락 — 비중 축소', quantity: 0.053, price: 342_000, fee: 3, status: '체결완료' },
  { id: 'tx-11', date: '2026.07.08', type: '배당', stockName: '삼성전자', amount: 1_250, note: '분기 배당금 입금', quantity: 0, price: 0, fee: 0, status: '체결완료' },
  { id: 'tx-12', date: '2026.07.04', type: '매수', stockName: 'POSCO홀딩스', amount: 28_000, note: '정기 적립 매수', quantity: 0.097, price: 289_500, fee: 4, status: '체결완료' },
  { id: 'tx-13', date: '2026.06.30', type: '매도', stockName: '삼성바이오로직스', amount: -32_000, note: '비중 축소', quantity: 0.039, price: 812_000, fee: 5, status: '체결완료' },
  { id: 'tx-14', date: '2026.06.26', type: '매수', stockName: 'KB금융', amount: 20_000, note: '정기 적립 매수', quantity: 0.236, price: 84_600, fee: 3, status: '체결완료' },
  { id: 'tx-15', date: '2026.06.22', type: '매수', stockName: '신한지주', amount: 18_000, note: '정기 적립 매수', quantity: 0.344, price: 52_400, fee: 3, status: '체결완료' },
  { id: 'tx-16', date: '2026.06.18', type: '배당', stockName: '하나금융지주', amount: 1_580, note: '분기 배당금 입금', quantity: 0, price: 0, fee: 0, status: '체결완료' },
  { id: 'tx-17', date: '2026.06.14', type: '매수', stockName: '삼성화재', amount: 22_000, note: '정기 적립 매수', quantity: 0.063, price: 348_000, fee: 3, status: '체결완료' },
  { id: 'tx-18', date: '2026.06.10', type: '매도', stockName: 'LG전자', amount: -12_000, note: '비중 조정', quantity: 0.122, price: 98_700, fee: 2, status: '체결완료' },
  { id: 'tx-19', date: '2026.06.06', type: '리밸런싱', stockName: '한국전력', amount: -8_000, note: 'AI 리밸런싱 제안 수락 — 비중 축소', quantity: 0.358, price: 22_350, fee: 1, status: '체결완료' },
  { id: 'tx-20', date: '2026.06.02', type: '매수', stockName: '유한양행', amount: 16_000, note: '정기 적립 매수', quantity: 0.135, price: 118_400, fee: 2, status: '체결완료' },
];
