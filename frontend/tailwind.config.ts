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
      borderRadius: { card: '24px', field: '12px' },
    },
  },
  plugins: [],
} satisfies Config;
