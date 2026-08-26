import type { Config } from 'tailwindcss';

/** 디자인 시스템 토큰 — 이 팔레트 밖의 색은 사용하지 않는다 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        lime: '#C6F04D',      // 선택 / AI 추천 / Primary CTA 에만
        navy: '#18243A',
        canvas: '#FAFBF8',
        surface: '#FFFFFF',
        ink: '#17211C',
        muted: '#5C665F',
        subtle: '#8A948C',
        line: '#E5E9E3',
        up: '#E5484D',        // 상승 (semantic)
        down: '#3578E5',      // 하락 (semantic)
        warn: '#E9A23B',
      },
      // field/card 두 토큰만으로는 실제 화면에서 쓰이는 폭을 못 담아 rounded-[9px]~[22px]까지
      // 12개 넘는 임의 값이 흩어져 있었다(#131 감리 참고). 그 값들을 대표하는 2단계를 사이에 끼워
      // 4단 스케일로 정리한다 — 기존 파일은 건드리지 않고(마이그레이션은 별도 이슈), 새 코드부터
      // 이 4개 중에서 고른다: field-sm(아이콘 버튼/작은 뱃지) < field(기본 버튼·입력) <
      // panel(카드 내부 서브 섹션·하이라이트 블록) < card(카드/모달 컨테이너).
      borderRadius: {
        field: '12px',
        card: '24px',
        'field-sm': '9px',
        panel: '18px',
      },
      // "떠 있는" 정도를 나타내는 shadow 13종이 컴포넌트마다 다른 rgba였다 — sm/md/lg 3단으로
      // 정리한다. 카드 테두리(1px inset)·선택 상태(2px lime inset)는 elevation이 아니라 "테두리
      // 표현"이라 이 스케일에 넣지 않고 각자 화면에서 계속 shadow-[0_0_0_1px_...] 형태로 쓴다.
      boxShadow: {
        'elevation-sm': '0 2px 8px rgba(24,36,58,0.08)',   // 드롭다운, 작은 팝오버
        'elevation-md': '0 8px 24px rgba(24,36,58,0.18)',  // 카드 위 카드, 툴팁, 배지
        'elevation-lg': '0 20px 60px rgba(24,36,58,0.18)', // 모달, 챗봇 패널처럼 화면을 덮는 레이어
      },
      // H1에 이름 없이 5가지 크기(56/44/40/38/34px)가 흩어져 있었다 — 실제 쓰이던 값 그대로
      // 이름만 붙인다(사이즈를 줄이는 마이그레이션은 하지 않음). [fontSize, {lineHeight, letterSpacing}]
      // 형태라 text-display-lg 하나로 font-size/line-height/letter-spacing이 함께 적용된다.
      fontSize: {
        'display-lg': ['56px', { lineHeight: '74px', letterSpacing: '-0.04em' }],  // Home 히어로
        display: ['44px', { lineHeight: '62px', letterSpacing: '-0.035em' }],       // 가장 흔한 H1
        heading: ['40px', { lineHeight: '56px', letterSpacing: '-0.035em' }],
        'heading-sm': ['38px', { lineHeight: '52px', letterSpacing: '-0.035em' }],
        subheading: ['34px', { lineHeight: '46px', letterSpacing: '-0.03em' }],     // 상세 화면 페이지 제목
      },
    },
  },
  plugins: [],
} satisfies Config;
