/** vitest 는 기본적으로 node 환경에서 돈다 — localStorage 는 Node 에 없고(sessionStorage 는 있지만
 *  세션 간 격리를 보장하려면 마찬가지로 매 테스트 새 인스턴스가 낫다), authStore.ts 는 모듈 로드 시점에
 *  바로 localStorage.getItem 을 호출한다. jsdom 의존성을 추가하는 대신 최소한의 in-memory Storage 구현으로
 *  전역을 채워, 브라우저 전용 스토리지 API 에 의존하는 스토어를 그대로 테스트할 수 있게 한다. */
class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

Object.defineProperty(globalThis, 'localStorage', { value: new MemoryStorage(), configurable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: new MemoryStorage(), configurable: true });
