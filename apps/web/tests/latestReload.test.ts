import { expect, it, vi } from 'vitest';
import { createLatestReload } from '../lib/latestReload';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// #699 SHR-032: 실시간 이벤트로 시작된 재조회가 진행 중일 때 메모 PATCH가 끝나고 `reload()`를 부르면,
// 그 호출은 PATCH 전에 출발한 조회 결과(메모 없음)로 끝나면 안 된다.
it('진행 중 조회보다 늦게 부른 reload는 그 뒤에 출발한 조회 결과로 끝난다', async () => {
  const calls: ReturnType<typeof deferred<string>>[] = [];
  const reload = createLatestReload(() => {
    const call = deferred<string>();
    calls.push(call);
    return call.promise;
  });

  const early = reload(); // 실시간 재조회(PATCH 전 출발)
  expect(calls).toHaveLength(1);
  const afterSave = reload(); // PATCH 성공 뒤
  const alsoAfterSave = reload(); // 같은 대기 조회에 합류
  expect(calls).toHaveLength(1); // 동시 조회는 하나뿐

  calls[0]!.resolve('메모 없음');
  expect(await early).toBe('메모 없음');
  await vi.waitFor(() => expect(calls).toHaveLength(2)); // 끝난 뒤 한 번 더 읽는다
  calls[1]!.resolve('메모 있음');
  expect(await afterSave).toBe('메모 있음');
  expect(await alsoAfterSave).toBe('메모 있음');

  // 진행 중이 없으면 새로 하나만 읽는다.
  const later = reload();
  expect(calls).toHaveLength(3);
  calls[2]!.resolve('최신');
  expect(await later).toBe('최신');
});

it('진행 중 조회가 실패해도 대기한 reload는 새로 읽는다', async () => {
  const calls: ReturnType<typeof deferred<string>>[] = [];
  const reload = createLatestReload(() => {
    const call = deferred<string>();
    calls.push(call);
    return call.promise;
  });
  const early = reload();
  const queued = reload();
  calls[0]!.reject(new Error('fixture'));
  await expect(early).rejects.toThrow('fixture');
  await vi.waitFor(() => expect(calls).toHaveLength(2));
  calls[1]!.resolve('복구');
  expect(await queued).toBe('복구');
});
