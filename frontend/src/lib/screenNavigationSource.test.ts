import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const APP_SOURCE = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");

describe("App screen navigation boundary", () => {
  it("does not reintroduce the legacy setScreen navigation path", () => {
    expect(APP_SOURCE).not.toMatch(/\bsetScreen\s*\(/);
  });

  it("keeps raw screen state writes inside navigation and popstate adapters", () => {
    expect(APP_SOURCE.match(/\bsetScreenState\s*\(/g)).toHaveLength(4);

    const renderSource = APP_SOURCE.slice(
      APP_SOURCE.indexOf("  return (\n    <div"),
    );
    expect(renderSource).not.toMatch(/\bsetScreenState\s*\(/);
  });
});
