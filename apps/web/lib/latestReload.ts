/**
 * 겹치는 재조회를 합치되, **호출 뒤에 출발한** 조회 결과로만 끝나게 한다(#699).
 *
 * 진행 중인 조회는 호출보다 먼저 출발했다. 그 사이 끝난 변경(POI 메모 PATCH 등)을 보지 못했을 수 있으므로
 * 진행 중 조회에 그대로 합류하면 낡은 여행 데이터로 끝난다 — 실시간 이벤트로 시작된 재조회가 저장 직후
 * `reload()`를 삼켜 내보내기 미리보기가 방금 저장한 메모를 빠뜨렸다. 진행 중이면 끝난 뒤 **한 번 더**
 * 조회하고, 그 사이 들어온 호출은 모두 그 다음 조회 하나에 합류한다(동시 조회는 최대 1 + 대기 1).
 */
export function createLatestReload<T>(fetchOnce: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  let queued: Promise<T> | null = null;

  const start = (): Promise<T> => {
    const tracked = fetchOnce().finally(() => {
      if (inFlight === tracked) inFlight = null;
    });
    inFlight = tracked;
    return tracked;
  };

  return () => {
    if (!inFlight) return start();
    if (queued) return queued;
    const next = inFlight
      .catch(() => undefined)
      .then(() => {
        if (queued === next) queued = null;
        return start();
      });
    queued = next;
    return next;
  };
}

/**
 * `createLatestReload`에 조회 출발 순번을 붙인다(#733). 순번은 1부터 출발 순서대로 늘고, `startedFetches()`는
 * 지금까지 출발한 조회 수다 — 어떤 변경이 어느 조회보다 늦게 끝났는지(그 조회 결과가 변경을 모르는지) 가린다.
 */
export function createSequencedReload<T>(
  fetchOnce: (seq: number) => Promise<T>,
): { reload: () => Promise<T>; startedFetches: () => number } {
  let started = 0;
  const reload = createLatestReload(() => {
    started += 1;
    return fetchOnce(started);
  });
  return { reload, startedFetches: () => started };
}
