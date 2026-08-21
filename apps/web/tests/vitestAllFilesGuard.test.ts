import { afterEach, describe, expect, it, vi } from 'vitest';
import { AssertAllPlannedFilesRan, findUnrunModules } from '../vitest.reporters';

/**
 * T-321 가드의 판정 로직. 리포터 본체는 vitest 내부 이벤트에 붙어 있어 단위 테스트로 돌리기
 * 어렵지만, "무엇을 누락으로 볼 것인가"는 순수 함수라 여기서 고정한다.
 */
describe('findUnrunModules', () => {
  it('결과가 없는 계획 파일을 집어낸다', () => {
    expect(findUnrunModules(['/a.test.ts', '/b.test.ts', '/c.test.ts'], ['/a.test.ts'])).toEqual([
      '/b.test.ts',
      '/c.test.ts',
    ]);
  });

  it('전부 실행되면 빈 배열이다', () => {
    expect(findUnrunModules(['/a.test.ts', '/b.test.ts'], ['/b.test.ts', '/a.test.ts'])).toEqual(
      [],
    );
  });

  it('부분 실행(계획 자체가 1건)은 누락이 아니다', () => {
    // CLI 필터가 걸리면 계획 집합이 이미 좁혀져 오므로 가드가 오탐하지 않는다.
    expect(findUnrunModules(['/a.test.ts'], ['/a.test.ts'])).toEqual([]);
  });

  it('계획에 없는 결과가 섞여도 누락 판정에 영향이 없다', () => {
    expect(findUnrunModules(['/a.test.ts'], ['/a.test.ts', '/extra.test.ts'])).toEqual([]);
  });

  it('중복 계획은 한 번만 보고한다', () => {
    expect(findUnrunModules(['/a.test.ts', '/a.test.ts'], [])).toEqual(['/a.test.ts']);
  });
});

describe('AssertAllPlannedFilesRan', () => {
  // 가드는 성공/실패를 `process.exitCode`로 표현한다. 이 테스트는 그 부작용을 일으키므로
  // 워커의 종료 코드가 오염되지 않게 매번 되돌린다.
  const original = process.exitCode;
  afterEach(() => {
    process.exitCode = original;
    vi.restoreAllMocks();
  });

  function run(planned: string[], ran: string[], reason: 'passed' | 'interrupted' | 'failed') {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const reporter = new AssertAllPlannedFilesRan();
    reporter.onTestRunStart(planned.map((moduleId) => ({ moduleId })) as never);
    reporter.onTestRunEnd(ran.map((moduleId) => ({ moduleId })) as never, [], reason);
    return errors;
  }

  it('결과 없는 계획 파일이 있으면 실행을 실패로 만든다', () => {
    const errors = run(['/a.test.ts', '/b.test.ts'], ['/a.test.ts'], 'passed');
    expect(process.exitCode).toBe(1);
    expect(errors).toHaveBeenCalledOnce();
    expect(String(errors.mock.calls[0]?.[0])).toContain('/b.test.ts');
  });

  it('전부 실행되면 종료 코드를 건드리지 않는다', () => {
    const errors = run(['/a.test.ts'], ['/a.test.ts'], 'passed');
    expect(process.exitCode).toBe(original);
    expect(errors).not.toHaveBeenCalled();
  });

  it('사용자가 끊은 실행(interrupted)은 누락으로 보지 않는다', () => {
    const errors = run(['/a.test.ts', '/b.test.ts'], [], 'interrupted');
    expect(process.exitCode).toBe(original);
    expect(errors).not.toHaveBeenCalled();
  });
});
