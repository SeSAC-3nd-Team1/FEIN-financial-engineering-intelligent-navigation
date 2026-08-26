#!/usr/bin/env node
/**
 * tailwind.config.ts: "이 팔레트 밖의 색은 사용하지 않는다" — 이 규칙을 CI에서 강제한다.
 *
 * src/pages, src/components 안에서 등장하는 raw hex(#RRGGBB) 리터럴을 전부 모아, tailwind.config.ts의
 * colors 토큰에 등록된 값과 대조한다. 등록 안 된 hex가 하나라도 있으면 실패한다 — 새 화면을 만들 때
 * "일단 눈대중 색을 하나 더 쓰고 나중에 정리하자"가 반복되는 걸 막기 위한 최소한의 가드레일이다.
 *
 * 등록된 값이라도 "토큰 클래스(bg-lime 등)를 안 쓰고 raw hex(#C6F04D)로 다시 타이핑한" 경우까지는 잡지
 * 않는다 — 그건 정적으로 안전하게 구분하기 어렵고(어떤 유틸리티 접두사와 짝지어야 하는지 케이스가 많다),
 * 기존 코드 전체를 건드리는 마이그레이션이 필요한 별도 작업이다(이 리포의 이슈 #140 참고).
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_ROOT = fileURLToPath(new URL('..', import.meta.url));
const SCAN_DIRS = ['src/pages', 'src/components'];
const HEX_RE = /#[0-9A-Fa-f]{6}\b/g;

function collectFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) out.push(...collectFiles(full));
    else if (['.tsx', '.ts'].includes(extname(full))) out.push(full);
  }
  return out;
}

function knownPaletteHexes() {
  const configPath = join(FRONTEND_ROOT, 'tailwind.config.ts');
  const source = readFileSync(configPath, 'utf8');
  const matches = source.match(HEX_RE) ?? [];
  return new Set(matches.map((h) => h.toUpperCase()));
}

function main() {
  const known = knownPaletteHexes();
  const files = SCAN_DIRS.flatMap((dir) => collectFiles(join(FRONTEND_ROOT, dir)));

  const violations = [];
  for (const file of files) {
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      const found = line.match(HEX_RE) ?? [];
      for (const hex of found) {
        if (!known.has(hex.toUpperCase())) {
          violations.push({ file: file.replace(FRONTEND_ROOT, ''), line: i + 1, hex, text: line.trim() });
        }
      }
    });
  }

  if (violations.length === 0) {
    console.log(`OK — 팔레트 밖 raw hex 없음 (검사 파일 ${files.length}개, 등록된 토큰 hex ${known.size}개)`);
    return;
  }

  console.error(`팔레트 밖 raw hex ${violations.length}건 발견 — tailwind.config.ts의 colors에 토큰으로 추가하거나, 이미 있는 토큰 클래스를 쓰세요.\n`);
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}  ${v.hex}\n    ${v.text}`);
  }
  process.exitCode = 1;
}

main();
