import { describe, expect, it } from "vitest";

import { fetchKnowledge, KNOWLEDGE_CONTENT } from "./informationApi";

describe("financial education content policy", () => {
  it("publishes traceable reviewed metadata for every article", async () => {
    const response = await fetchKnowledge();

    expect(response.items).toHaveLength(KNOWLEDGE_CONTENT.totalCount);
    expect(response.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          sourceName: expect.any(String),
          sourceUrl: expect.stringMatching(/^https:\/\//),
          reviewedAt: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
          contentVersion: expect.stringMatching(/^education-v\d+$/),
        }),
      ]),
    );
    for (const item of response.items) {
      expect(item.sourceName.trim()).not.toBe("");
      expect(item.sourceUrl).toMatch(/^https:\/\//);
      expect(item.reviewedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(item.contentVersion).toMatch(/^education-v\d+$/);
      expect(item.sourceUrl).not.toContain("example.com");
      expect(item.sourceUrl).not.toMatch(
        /^https:\/\/www\.(krx|fss|nts)\.or\.kr\/?$/,
      );
    }

    const perArticle = response.items.find((item) => item.id === "k1");
    expect(perArticle?.sourceUrl).toContain("data.krx.co.kr");
    expect(perArticle?.sourceUrl).toContain("MDC0201020102");
  });
});
