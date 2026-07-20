import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useModalDialog } from '@/lib/useModalDialog';

function Harness(props: { onClose: () => void; ariaLabel?: string; idPrefix?: string }) {
  const p = props.idPrefix ?? '';
  const { titleId, backdropProps, dialogProps } = useModalDialog({
    onClose: props.onClose,
    ariaLabel: props.ariaLabel,
  });
  return (
    <div data-testid={`${p}backdrop`} {...backdropProps}>
      <div {...dialogProps} data-testid={`${p}panel`}>
        {props.ariaLabel == null && <h2 id={titleId}>제목</h2>}
        <button data-testid={`${p}first`}>first</button>
        <button data-testid={`${p}last`}>last</button>
      </div>
    </div>
  );
}

describe('useModalDialog', () => {
  it('Escape로 onClose를 호출한다', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('backdrop에서 눌러 backdrop에서 놓으면 닫는다', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const backdrop = screen.getByTestId('backdrop');
    fireEvent.mouseDown(backdrop);
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('패널 안에서 눌러 backdrop에서 놓으면(드래그) 닫지 않는다', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const backdrop = screen.getByTestId('backdrop');
    fireEvent.mouseDown(screen.getByTestId('panel'));
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('패널 클릭으로는 닫지 않는다', () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const panel = screen.getByTestId('panel');
    fireEvent.mouseDown(panel);
    fireEvent.click(panel);
    expect(onClose).not.toHaveBeenCalled();
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

  it('열리면 body 스크롤을 잠그고 닫히면 복원한다', () => {
    expect(document.body.style.overflow).toBe('');
    const { unmount } = render(<Harness onClose={vi.fn()} />);
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('');
  });

  it('열리면 패널로 포커스를 옮긴다', async () => {
    render(<Harness onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId('panel')).toHaveFocus());
  });

  it('마지막 요소에서 Tab하면 첫 요소로 순환한다', () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('last').focus();
    fireEvent.keyDown(document.body, { key: 'Tab' });
    expect(screen.getByTestId('first')).toHaveFocus();
  });

  it('첫 요소에서 Shift+Tab하면 마지막 요소로 순환한다', () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('first').focus();
    fireEvent.keyDown(document.body, { key: 'Tab', shiftKey: true });
    expect(screen.getByTestId('last')).toHaveFocus();
  });

  it('패널에 포커스가 있을 때 Shift+Tab하면 마지막 요소로 가둔다(뒤로 누수 방지)', () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('panel').focus();
    fireEvent.keyDown(document.body, { key: 'Tab', shiftKey: true });
    expect(screen.getByTestId('last')).toHaveFocus();
  });

  it('패널에 포커스가 있을 때 Tab하면 첫 요소로 가둔다', () => {
    render(<Harness onClose={vi.fn()} />);
    screen.getByTestId('panel').focus();
    fireEvent.keyDown(document.body, { key: 'Tab' });
    expect(screen.getByTestId('first')).toHaveFocus();
  });

  it('중첩 모달에서 Escape는 최상단 하나만 닫는다', () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();
    render(
      <>
        <Harness onClose={onCloseA} idPrefix="a-" />
        <Harness onClose={onCloseB} idPrefix="b-" />
      </>,
    );
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(onCloseB).toHaveBeenCalledTimes(1);
    expect(onCloseA).not.toHaveBeenCalled();
  });
});
