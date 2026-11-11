import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { isRestorableFocusTarget } from '@/lib/focusTarget';
import { Dialog } from '@/components/ui/Dialog';
import { useRef, useState } from 'react';
import userEvent from '@testing-library/user-event';

function Harness(props: {
  onClose: () => void;
  ariaLabel?: string;
  idPrefix?: string;
  busy?: boolean;
}) {
  const p = props.idPrefix ?? '';
  return (
    <Dialog
      open
      onClose={props.onClose}
      title="제목"
      ariaLabel={props.ariaLabel}
      showClose={false}
      testId={p + 'panel'}
      busy={props.busy}
    >
      <button data-testid={p + 'first'}>first</button>
      <button data-testid={p + 'last'}>last</button>
    </Dialog>
  );
}
function backdrop(prefix = '') {
  return screen.getByTestId(prefix + 'panel-backdrop');
}

describe('공통 Radix 공개 Dialog 행동 계약', () => {
  it('저장 시작으로 포커스한 버튼이 비활성화되면 busy 패널로 옮긴다', async () => {
    const onClose = vi.fn();
    function BusyForm() {
      const [busy, setBusy] = useState(false);
      return (
        <Dialog open title="저장" onClose={onClose} busy={busy} onCancelBusy={vi.fn()}>
          <button disabled={busy} onClick={() => setBusy(true)}>
            저장 시작
          </button>
        </Dialog>
      );
    }
    const user = userEvent.setup();
    render(<BusyForm />);
    const save = screen.getByRole('button', { name: '저장 시작' });
    await user.click(save);
    expect(save).toBeDisabled();
    expect(screen.getByRole('dialog')).toHaveFocus();
    await user.click(screen.getByTestId('dialog-backdrop'));
    expect(screen.getByRole('dialog')).toHaveFocus();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('숨겨진 대상은 focus 복원 대상으로 취급하지 않는다', () => {
    const target = document.createElement('button');
    document.body.append(target);
    const getClientRects = vi
      .spyOn(target, 'getClientRects')
      .mockReturnValue([{}] as unknown as DOMRectList);
    target.style.display = 'none';
    expect(isRestorableFocusTarget(target)).toBe(false);
    target.style.display = '';
    target.style.visibility = 'hidden';
    expect(isRestorableFocusTarget(target)).toBe(false);
    target.style.visibility = '';
    expect(isRestorableFocusTarget(target)).toBe(true);
    getClientRects.mockRestore();
    target.remove();
  });

  it('Escape로 onClose를 호출한다', async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent.setup().keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('backdrop에서 눌러 backdrop에서 놓으면 닫는다', async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const overlay = backdrop();
    await userEvent.setup().click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('패널 안에서 눌러 backdrop에서 놓으면(드래그) 닫지 않는다', async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const overlay = backdrop();
    await userEvent
      .setup()
      .pointer([
        { keys: '[MouseLeft>]', target: screen.getByTestId('panel') },
        { target: overlay },
        { keys: '[/MouseLeft]', target: overlay },
      ]);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('패널 클릭으로는 닫지 않는다', async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const panel = screen.getByTestId('panel');
    await userEvent.setup().click(panel);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('설명과 aria-describedby를 같은 실제 요소로 연결한다', () => {
    render(
      <Dialog open onClose={vi.fn()} title="설명 제목" description="작업 설명">
        본문
      </Dialog>,
    );
    const panel = screen.getByRole('dialog', { name: '설명 제목' });
    expect(panel).toHaveAccessibleDescription('작업 설명');
    expect(document.getElementById(panel.getAttribute('aria-describedby') ?? '')).toHaveTextContent(
      '작업 설명',
    );
  });

  it('기본은 heading을 aria-labelledby로 연결한다', () => {
    render(<Harness onClose={vi.fn()} />);
    const panel = screen.getByTestId('panel');
    expect(panel).toHaveAttribute('role', 'dialog');
    expect(panel).toHaveAttribute('aria-modal', 'true');
    const labelledBy = panel.getAttribute('aria-labelledby');
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)).toHaveTextContent('제목');
    expect(panel).not.toHaveAttribute('aria-label');
  });

  it('ariaLabel을 주면 aria-label을 쓰고 labelledby는 없다', () => {
    render(<Harness onClose={vi.fn()} ariaLabel="내 모달" />);
    const panel = screen.getByTestId('panel');
    expect(panel).toHaveAttribute('aria-label', '내 모달');
    expect(panel).not.toHaveAttribute('aria-labelledby');
  });

  it('열리면 배경 스크롤을 잠그고 닫히면 복원한다', () => {
    const body = document.body;
    expect(body).not.toHaveAttribute('data-scroll-locked');
    const { unmount } = render(<Harness onClose={vi.fn()} />);
    expect(body).toHaveAttribute('data-scroll-locked');
    unmount();
    expect(body).not.toHaveAttribute('data-scroll-locked');
  });

  it('열리면 패널로 포커스를 옮긴다', async () => {
    render(<Harness onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId('panel')).toHaveFocus());
  });

  it('마지막 요소에서 Tab하면 첫 요소로 순환한다', async () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('last').focus();
    await userEvent.setup().tab();
    expect(screen.getByTestId('first')).toHaveFocus();
  });

  it('첫 요소에서 Shift+Tab하면 마지막 요소로 순환한다', async () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('first').focus();
    await userEvent.setup().tab({ shift: true });
    expect(screen.getByTestId('last')).toHaveFocus();
  });

  it('패널에 포커스가 있을 때 Shift+Tab하면 마지막 요소로 가둔다(뒤로 누수 방지)', async () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('panel').focus();
    await userEvent.setup().tab({ shift: true });
    expect(screen.getByTestId('last')).toHaveFocus();
  });

  it('disabled fieldset의 자손은 역방향 포커스 경계에서 제외한다', async () => {
    render(
      <Dialog open title="비활성 그룹" onClose={vi.fn()} showClose={false}>
        <button>활성 경계</button>
        <fieldset disabled>
          <legend>비활성 그룹</legend>
          <button>비활성 자손</button>
        </fieldset>
      </Dialog>,
    );
    screen.getByRole('dialog').focus();
    await userEvent.setup().tab({ shift: true });
    expect(screen.getByRole('button', { name: '활성 경계' })).toHaveFocus();
    expect(screen.getByRole('button', { name: '비활성 자손' })).toBeDisabled();
  });

  it('disabled fieldset의 첫 legend 내부는 활성 포커스 경계로 유지한다', async () => {
    render(
      <Dialog open title="첫 범례 예외" onClose={vi.fn()} showClose={false}>
        <button>그룹 앞</button>
        <fieldset disabled>
          <legend><button>활성 범례</button></legend>
          <button>비활성 자손</button>
        </fieldset>
      </Dialog>,
    );
    screen.getByRole('dialog').focus();
    await userEvent.setup().tab({ shift: true });
    expect(screen.getByRole('button', { name: '활성 범례' })).toHaveFocus();
    expect(screen.getByRole('button', { name: '비활성 자손' })).toBeDisabled();
  });

  it('패널에 포커스가 있을 때 Tab하면 첫 요소로 가둔다', async () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('panel').focus();
    await userEvent.setup().tab();
    expect(screen.getByTestId('first')).toHaveFocus();
  });

  it('중첩 모달에서 Escape는 최상단 하나만 닫는다', async () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();
    render(
      <>
        <Harness onClose={onCloseA} idPrefix="a-" />
        <Harness onClose={onCloseB} idPrefix="b-" />
      </>,
    );
    await userEvent.setup().keyboard('{Escape}');
    expect(onCloseB).toHaveBeenCalledTimes(1);
    expect(onCloseA).not.toHaveBeenCalled();
  });
});

describe('공개 Dialog 도메인 정책', () => {
  it('busy이면 Escape/바깥 클릭/명시적 닫기를 잠근다', async () => {
    const close = vi.fn(),
      user = userEvent.setup();
    render(
      <Dialog open busy title="저장" onClose={close}>
        <input aria-label="이름" />
      </Dialog>,
    );
    await user.keyboard('{Escape}');
    await user.click(screen.getByTestId('dialog-backdrop'));
    expect(screen.getByTestId('dialog-close')).toBeDisabled();
    expect(close).not.toHaveBeenCalled();
  });
  it('onCancelBusy가 있으면 명시적 닫기만 취소 경로를 호출한다', async () => {
    const close = vi.fn(),
      cancel = vi.fn(),
      user = userEvent.setup();
    render(<Dialog open busy title="저장" onClose={close} onCancelBusy={cancel} />);
    await user.keyboard('{Escape}');
    await user.click(screen.getByTestId('dialog-backdrop'));
    expect(cancel).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '취소하고 닫기' }));
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
  });
  it('scrim에서 시작해 패널로 놓는 drag도 실수 닫기로 처리하지 않는다', async () => {
    const close = vi.fn(),
      user = userEvent.setup();
    render(<Dialog open title="제목" onClose={close} />);
    const overlay = screen.getByTestId('dialog-backdrop'),
      panel = screen.getByTestId('dialog');
    await user.pointer([
      { keys: '[MouseLeft>]', target: overlay },
      { target: panel },
      { keys: '[/MouseLeft]', target: panel },
    ]);
    expect(close).not.toHaveBeenCalled();
  });
  it('명시한 초기 입력으로 포커스를 옮긴다', () => {
    function Form() {
      const initial = useRef<HTMLInputElement>(null);
      return (
        <Dialog open title="입력" onClose={() => {}} initialFocusRef={initial}>
          <input ref={initial} aria-label="이름" />
        </Dialog>
      );
    }
    render(<Form />);
    expect(screen.getByRole('textbox', { name: '이름' })).toHaveFocus();
  });
  it('sheet의 하단·데스크톱 중앙 표현과 본문스크롤 계약을 유지한다', () => {
    render(
      <Dialog open variant="sheet" title="장소" onClose={() => {}}>
        <p>본문</p>
      </Dialog>,
    );
    expect(screen.getByTestId('dialog')).toHaveClass('bottom-0', 'sm:top-1/2', 'max-h-[88dvh]');
    expect(screen.getByText('본문').parentElement).toHaveClass('overflow-auto');
  });
  it('아래 모달 busy 변경이 최상단 Escape 우선순위를 뒤집지 않는다', async () => {
    const a = vi.fn(),
      b = vi.fn();
    const { rerender } = render(
      <>
        <Harness idPrefix="a-" onClose={a} />
        <Harness idPrefix="b-" onClose={b} />
      </>,
    );
    expect(screen.getByTestId('b-panel')).toHaveFocus();
    rerender(
      <>
        <Harness idPrefix="a-" onClose={a} busy />
        <Harness idPrefix="b-" onClose={b} />
      </>,
    );
    expect(screen.getByTestId('b-panel')).toHaveFocus();
    await userEvent.setup().keyboard('{Escape}');
    expect(b).toHaveBeenCalledTimes(1);
    expect(a).not.toHaveBeenCalled();
  });
  it('닫은 뒤 활성화된 opener로 포커스를 복원한다', async () => {
    const rects = vi
      .spyOn(HTMLElement.prototype, 'getClientRects')
      .mockReturnValue([{}] as unknown as DOMRectList);
    function Page() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} disabled={open}>
            열기
          </button>
          <Dialog open={open} title="확인" onClose={() => setOpen(false)} />
        </>
      );
    }
    try {
      render(<Page />);
      const user = userEvent.setup(),
        opener = screen.getByRole('button', { name: '열기' });
      await user.click(opener);
      await user.click(screen.getByTestId('dialog-close'));
      await waitFor(() => expect(opener).toHaveFocus());
    } finally {
      rects.mockRestore();
    }
  });
});
