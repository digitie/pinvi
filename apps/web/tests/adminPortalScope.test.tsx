import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Dialog, DialogContent, DialogTitle } from '@/components/admin/ui/dialog';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
} from '@/components/admin/ui/alert-dialog';

/**
 * 포털된 오버레이가 admin 타이포 scope 안에 남는지 **실제 렌더로** 검사한다(T-356).
 *
 * `tests/adminTypographyScope.test.ts`는 globals.css 텍스트만 읽으므로 "스코프 선언이 존재하는가"
 * 까지만 본다. 그런데 base-ui `Portal`의 기본 컨테이너는 `<body>`라, 선언이 멀쩡해도 포털된
 * 팝업은 `app/(admin)/layout.tsx`의 `[data-pv-surface="admin"]` **DOM 하위가 아니게 된다**.
 * 그러면 모달 안에서만 `--text-sm` 15px→14px, `--text-xs` 13.5px→12px로 줄어든다. 색 토큰은
 * `@theme`(`:root`)라 멀쩡해서 "제목은 정상인데 본문만 작은" 모달이 되고, 어느 정적 게이트도
 * 잡지 못한다.
 *
 * 그래서 `closest()`로 조상 체인을 직접 확인한다. 이 검사는 스코프를 라우트 레이아웃에만
 * 의존하지 않고 팝업 자신이 표식을 갖는지 보므로, portal 컨테이너 구현이 바뀌어도 유효하다.
 */
const SCOPE = '[data-pv-surface="admin"]';

describe('admin 오버레이 포털 스코프', () => {
  it('Dialog 팝업이 admin scope 안에 있다', () => {
    render(
      <Dialog open onOpenChange={() => {}}>
        <DialogContent data-testid="panel">
          <DialogTitle>제목</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    const panel = screen.getByTestId('panel');
    expect(
      panel.closest(SCOPE),
      'portal이 body로 나가면서 admin 타이포 스케일이 걸리지 않는다',
    ).not.toBeNull();
  });

  it('AlertDialog 팝업이 admin scope 안에 있다', () => {
    render(
      <AlertDialog open onOpenChange={() => {}}>
        <AlertDialogContent data-testid="alert-panel">
          <AlertDialogTitle>확인</AlertDialogTitle>
        </AlertDialogContent>
      </AlertDialog>,
    );

    const panel = screen.getByTestId('alert-panel');
    expect(panel.closest(SCOPE)).not.toBeNull();
  });

  it('실제로 body 바깥으로 포털된다 (이 검사가 무의미하지 않다는 확인)', () => {
    const { container } = render(
      <Dialog open onOpenChange={() => {}}>
        <DialogContent data-testid="panel2">
          <DialogTitle>제목</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    // 팝업이 render 컨테이너 안에 있으면 portal이 동작하지 않은 것이고, 그러면 위 두 검사가
    // 우연히 통과할 수 있다. portal이 실제로 일어남을 확인해 검사의 의미를 보장한다.
    expect(container.querySelector('[data-testid="panel2"]')).toBeNull();
    expect(screen.getByTestId('panel2')).toBeInTheDocument();
  });
});
