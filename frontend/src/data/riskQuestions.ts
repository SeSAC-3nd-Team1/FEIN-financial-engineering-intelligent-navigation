export interface RiskOption { title: string; desc: string; }
export interface RiskQuestion {
  q: string;
  support: string;
  visual?: 'loss';
  spectrum?: boolean;
  options?: RiskOption[];
}

/** 투자성향 진단 5문항 — 한 화면에 한 질문 */
export const RISK_QUESTIONS: RiskQuestion[] = [
  {
    q: '내 투자금 100만원이 85만원이 됐어요.\n어떻게 할 것 같나요?',
    support: '가장 가까운 행동을 골라주세요.',
    visual: 'loss',
    options: [
      { title: '바로 팔 것 같아요', desc: '더 떨어질까 봐 불안할 것 같아요.' },
      { title: '조금 더 지켜볼 것 같아요', desc: '이유를 확인한 뒤 결정하고 싶어요.' },
      { title: '오히려 더 살 수도 있어요', desc: '장기적으로 회복할 가능성을 생각해요.' },
    ],
  },
  {
    q: '이 돈은 언제쯤 필요할까요?',
    support: '지금 계획에 가장 가까운 걸 골라주세요.',
    options: [
      { title: '1년 안에', desc: '가까운 시일에 쓸 계획이 있어요.' },
      { title: '1~3년', desc: '중간에 필요해질 수도 있어요.' },
      { title: '3~5년', desc: '한동안은 묶어둘 수 있어요.' },
      { title: '5년 이상', desc: '당장 사용할 계획이 없는 돈이에요.' },
    ],
  },
  {
    q: '투자로 가장 얻고 싶은 건 무엇인가요?',
    support: '하나만 골라주세요.',
    options: [
      { title: '안정적으로 불리기', desc: '큰 손실 없이 천천히' },
      { title: '균형 있게 성장하기', desc: '수익과 안정성 둘 다' },
      { title: '적극적으로 키우기', desc: '변동성을 감수하고 높은 수익 추구' },
    ],
  },
  {
    q: '주식 투자는 얼마나 익숙한가요?',
    support: '설명 난이도를 맞추는 데 참고해요.',
    options: [
      { title: '처음이에요', desc: '투자를 거의 해본 적 없어요.' },
      { title: '조금 해봤어요', desc: '직접 주식을 사고팔아본 적 있어요.' },
      { title: '익숙해요', desc: '투자전략이나 지표도 어느 정도 이해해요.' },
    ],
  },
  {
    q: '시장이 크게 떨어졌다는 뉴스가 나왔어요.',
    support: '이럴 때 나는 어느 쪽에 더 가까울까요?',
    spectrum: true,
  },
];

export const SPECTRUM_LABELS = [
  '지금은 지키는 게 먼저예요',
  '조심스럽게 지켜볼 것 같아요',
  '상황을 보고 판단할 것 같아요',
  '떨어진 김에 조금 담아볼까 싶어요',
  '기회라고 생각하고 적극적으로 볼 거예요',
];
