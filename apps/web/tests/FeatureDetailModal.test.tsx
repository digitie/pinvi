import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { FeatureDetailModal } from '@/components/map/FeatureDetailModal';

describe('FeatureDetailModal', () => {
  it('open=false면 아무것도 렌더하지 않는다', () => {
    render(<FeatureDetailModal open={false} title="장소" onClose={vi.fn()} />);
    expect(screen.queryByTestId('feature-detail-modal')).not.toBeInTheDocument();
  });

  it('title/subtitle과 children을 렌더한다', () => {
    render(
      <FeatureDetailModal open title="한밭수목원" subtitle="대전 유성구" onClose={vi.fn()}>
        <p>상세 본문</p>
      </FeatureDetailModal>,
    );
    expect(screen.getByTestId('feature-detail-modal-title')).toHaveTextContent('한밭수목원');
    expect(screen.getByText('대전 유성구')).toBeInTheDocument();
    expect(screen.getByText('상세 본문')).toBeInTheDocument();
  });

  it('닫기 버튼이 onClose를 호출한다', () => {
    const onClose = vi.fn();
    render(<FeatureDetailModal open title="장소" onClose={onClose} />);
    fireEvent.click(screen.getByTestId('feature-detail-modal-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('loading이면 본문 대신 로딩을 표시한다', () => {
    render(
      <FeatureDetailModal open loading title="장소" onClose={vi.fn()}>
        <p>본문</p>
      </FeatureDetailModal>,
    );
    expect(screen.getByTestId('feature-detail-modal-loading')).toBeInTheDocument();
    expect(screen.queryByText('본문')).not.toBeInTheDocument();
  });

  it('error가 있으면 본문 대신 에러를 표시한다', () => {
    render(
      <FeatureDetailModal open error="불러오지 못했습니다." title="장소" onClose={vi.fn()}>
        <p>본문</p>
      </FeatureDetailModal>,
    );
    const err = screen.getByTestId('feature-detail-modal-error');
    expect(err).toHaveTextContent('불러오지 못했습니다.');
    expect(screen.queryByText('본문')).not.toBeInTheDocument();
  });

  it('footer가 있으면 렌더하고 없으면 렌더하지 않는다', () => {
    const { rerender } = render(
      <FeatureDetailModal open title="장소" onClose={vi.fn()} footer={<span>출처: Kakao</span>} />,
    );
    expect(screen.getByTestId('feature-detail-modal-footer')).toHaveTextContent('출처: Kakao');
    rerender(<FeatureDetailModal open title="장소" onClose={vi.fn()} />);
    expect(screen.queryByTestId('feature-detail-modal-footer')).not.toBeInTheDocument();
  });
});
