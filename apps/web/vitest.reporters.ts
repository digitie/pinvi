import type { Reporter, TestModule, TestSpecification, Vitest } from 'vitest/node';

/**
 * T-321 — "조용히 건너뛴 테스트 파일"을 실패로 만든다.
 *
 * vitest는 fork 워커 기동에 실패한 파일을 **결과 없이 버리고 exit 0**으로 끝낸다. 설치본
 * (`vitest/dist/chunks/cli-api.*.js`)에서 확인한 경로가 원인이다:
 *
 *   await runner.start(...).catch((error) => resolver.reject(
 *     new Error(`[vitest-pool]: Failed to start ${task.worker} worker for test files ...`)))
 *   ...
 *   await resolver.promise.catch((error) => span?.recordException(error))   // ← 여기서 삼켜진다
 *
 * rejection이 trace span에만 기록되고 실행 결과로 전파되지 않으므로 요약 줄
 * (`Test Files 15 passed (15)`)은 **실행된 것만** 센다. 사람도 CI도 누락을 알 수 없다.
 *
 * 그래서 실행 전 계획된 spec 집합과 실행 후 결과가 나온 module 집합을 대조한다. 계획 집합은
 * `onTestRunStart`가 주므로 CLI 파일 필터(`vitest run tests/foo.test.ts`)나 `-t` 필터가 걸린
 * 부분 실행에서도 오탐하지 않는다 — 필터링은 spec 목록 자체에 이미 반영돼 있다.
 */

/** 계획된 module id 중 결과가 없는 것. 순수 함수 — 단위 테스트가 이 로직을 고정한다. */
export function findUnrunModules(planned: Iterable<string>, ran: Iterable<string>): string[] {
  const done = new Set(ran);
  return [...new Set(planned)].filter((moduleId) => !done.has(moduleId));
}

export class AssertAllPlannedFilesRan implements Reporter {
  private planned: string[] = [];
  private sharded = false;

  onInit(vitest: Vitest): void {
    // `--shard`는 계획 대비 일부만 보고하는 것이 정상이므로 가드를 끈다.
    this.sharded = Boolean(vitest.config.shard);
  }

  onTestRunStart(specifications: ReadonlyArray<TestSpecification>): void {
    this.planned = specifications.map((spec) => spec.moduleId);
  }

  onTestRunEnd(
    testModules: ReadonlyArray<TestModule>,
    _unhandledErrors: ReadonlyArray<unknown>,
    reason: 'passed' | 'interrupted' | 'failed',
  ): void {
    // 사용자가 끊은 실행(Ctrl-C, watch 재시작)은 누락이 정상이다.
    if (reason === 'interrupted' || this.sharded) {
      return;
    }

    const missing = findUnrunModules(
      this.planned,
      testModules.map((mod) => mod.moduleId),
    );
    if (missing.length === 0) {
      return;
    }

    const list = missing.map((moduleId) => `  - ${moduleId}`).join('\n');
    console.error(
      `\n[T-321] 계획된 테스트 파일 ${missing.length}개가 결과 없이 끝났다 — ` +
        `요약 줄은 실행된 것만 세므로 이 실행을 성공으로 볼 수 없다:\n${list}\n` +
        '워커 기동 실패("[vitest-pool]: Failed to start ... worker")가 흔한 원인이다. ' +
        `위 로그에서 해당 메시지를 확인하고, 자원 압박이면 --maxWorkers를 낮춰 재실행한다.\n`,
    );
    // vitest는 exitCode를 1로 올리기만 하고 0으로 되돌리지 않으므로 여기서 실패를 확정할 수 있다.
    process.exitCode = 1;
  }
}
