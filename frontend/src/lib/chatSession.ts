export function chatConversationBoundaryKey(
  accessToken: string | null | undefined,
  accountId: string | undefined,
): string {
  return `${accessToken ?? "anonymous"}:${accountId ?? "no-account"}`;
}
