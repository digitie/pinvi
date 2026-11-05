import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { TripExportButton } from '../components/trips/TripExportButton';
import { exportSource } from './fixtures/tripExport';

afterEach(() => vi.restoreAllMocks());

it('미리보기·위치도와 메모를 고정하고 다시 열면 최신 내용을 사용한다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  const { rerender } = render(<TripExportButton view={source} />);
  // jsdom에는 layout rect가 없다. 실제로 보이는 trigger의 복원 경계를 모델링한다.
  vi.spyOn(screen.getByRole('button', { name: '여행 내보내기' }), 'getClientRects').mockReturnValue(
    [{}] as unknown as DOMRectList,
  );
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('일자 메모')).toBeInTheDocument();
  expect(within(dialog).getByText('장소 메모')).toBeInTheDocument();
  expect(within(dialog).getByRole('img', { name: '1일차 장소 위치도' })).toBeInTheDocument();
  const updated = exportSource();
  updated.trip.title = '수정한 제목';
  rerender(<TripExportButton view={updated} />);
  expect(within(dialog).getByRole('heading', { name: '부산 여행' })).toBeInTheDocument();
  expect(within(dialog).queryByText('수정한 제목')).not.toBeInTheDocument();
  await user.click(within(dialog).getByRole('button', { name: '닫기' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '여행 내보내기' })).toHaveFocus());
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  expect(await screen.findByRole('heading', { name: '수정한 제목' })).toBeInTheDocument();
});

it('잘못된 HTML·외부 URL은 정적 출력에서 실행 가능한 DOM이 되지 않는다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  source.trip.title = '<img src=x onerror=alert(1)>';
  source.days[0]!.pois[0]!.user_note = '<script>alert(2)</script>';
  source.days[0]!.pois[0]!.user_url = 'https://example.com/?token=secret';
  render(<TripExportButton view={source} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  const root = await screen.findByTestId('trip-export-document');
  expect(root.querySelector('img,script,a,iframe')).toBeNull();
  expect(root).toHaveTextContent('<img src=x onerror=alert(1)>');
  expect(root.innerHTML).not.toContain('secret');
});

it('날짜·시각 미정은 인쇄에는 남고 ICS에서는 제외 안내와 비활성 버튼을 보여준다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  source.trip.start_date = null;
  source.days[0]!.effective_date = null;
  source.days[0]!.pois[0]!.planned_arrival_at = null;
  source.days[0]!.pois[0]!.planned_departure_at = null;
  render(<TripExportButton view={source} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  expect(await screen.findByText(/날짜·시각 미정 1개는 ICS에서 제외/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'ICS 다운로드' })).toBeDisabled();
  expect(screen.getByTestId('trip-export-document')).toHaveTextContent('부산 장소');
});

it('좌표 없는 중간 방문을 빼더라도 뒤 장소의 방문 번호는 유지한다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  const first = source.days[0]!.pois[0]!;
  source.days[0]!.pois.push(
    {
      ...first,
      poi_id: '64100000-0000-4000-8000-000000000002',
      title: '좌표 없는 장소',
      sort_order: 'b',
      feature: {},
    },
    {
      ...first,
      poi_id: '64100000-0000-4000-8000-000000000003',
      title: '마지막 장소',
      sort_order: 'c',
      feature: { coord: { lon: 129.2, lat: 35.3 } },
    },
  );
  render(<TripExportButton view={source} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  const root = await screen.findByTestId('trip-export-document');
  expect(root.querySelector('svg')?.textContent).toContain('3.');
  expect(root).toHaveTextContent('좌표를 확인한 2/3곳');
  expect(root).toHaveTextContent('2. 좌표 없는 장소');
});

it('popup 차단을 원래 페이지 인쇄로 우회하지 않고 상세 원인을 보인다', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  const print = vi.spyOn(window, 'print').mockImplementation(() => {});
  const user = userEvent.setup();
  render(<TripExportButton view={exportSource()} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  await user.click(screen.getByRole('button', { name: '인쇄 / PDF 저장' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('팝업을 허용');
  expect(open).toHaveBeenCalledWith('about:blank', '_blank');
  expect(print).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '닫기' })).toBeEnabled();
});

it('인쇄 준비 중 명시적 취소가 popup을 닫고 미리보기도 닫는다', async () => {
  const doc = document.implementation.createHTMLDocument();
  Object.defineProperty(doc, 'fonts', { value: { ready: new Promise(() => {}) } });
  const popup = {
    document: doc,
    opener: window,
    focus: vi.fn(),
    print: vi.fn(),
    close: vi.fn(),
    closed: false,
  };
  vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
  const user = userEvent.setup();
  render(<TripExportButton view={exportSource()} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  fireEvent.click(screen.getByRole('button', { name: '인쇄 / PDF 저장' }));
  expect(await screen.findByRole('button', { name: '취소하고 닫기' })).toBeEnabled();
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '취소하고 닫기' }));
  });
  expect(popup.close).toHaveBeenCalled();
  expect(popup.print).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('선택·숨김과 관계없이 받은 전체 일자라는 범위를 명시한다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  source.days.push({
    ...source.days[0]!,
    day_index: 2,
    title: '숨긴 둘째날',
    effective_date: '2026-11-06',
    pois: [],
  });
  render(<TripExportButton view={source} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveTextContent('선택·숨김 상태와 관계없이 조회된 전체 일자를 포함합니다');
  expect(dialog).toHaveTextContent('숨긴 둘째날');
});

it('같은 위치 재방문의 번호를 한 표식에 함께 표시한다', async () => {
  const user = userEvent.setup();
  const source = exportSource();
  const first = source.days[0]!.pois[0]!;
  source.days[0]!.pois.push(
    {
      ...first,
      poi_id: '64100000-0000-4000-8000-000000000002',
      sort_order: 'b',
      title: '관광지',
      feature: { coord: { lon: 129.2, lat: 35.3 } },
    },
    {
      ...first,
      poi_id: '64100000-0000-4000-8000-000000000003',
      sort_order: 'c',
      title: '같은 숙소 재방문',
    },
  );
  render(<TripExportButton view={source} />);
  await user.click(screen.getByRole('button', { name: '여행 내보내기' }));
  const map = await screen.findByRole('img', { name: '1일차 장소 위치도' });
  const labels = Array.from(map.querySelectorAll('text')).map((text) => text.textContent);
  expect(labels).toEqual(['1·3', '2']);
});
