import { describe, expect, it } from "vitest";
import { chatConversationBoundaryKey } from "./chatSession";

describe("chat conversation boundary", () => {
  it("anonymous and authenticated conversations are isolated", () => {
    expect(chatConversationBoundaryKey(null, undefined)).not.toBe(
      chatConversationBoundaryKey("token-a", undefined),
    );
  });

  it("account changes create a new conversation boundary", () => {
    expect(chatConversationBoundaryKey("token-a", "account-a")).not.toBe(
      chatConversationBoundaryKey("token-a", "account-b"),
    );
  });

  it("same user and account keep the same boundary", () => {
    expect(chatConversationBoundaryKey("token-a", "account-a")).toBe(
      chatConversationBoundaryKey("token-a", "account-a"),
    );
  });
});
