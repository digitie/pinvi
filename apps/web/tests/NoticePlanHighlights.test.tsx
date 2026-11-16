import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import {
  NoticePlanHighlights,
  formatEventPeriod,
  formatNearDistance,
} from '@/components/notice-plans/NoticePlanHighlights';
import { NoticePlanShelf } from '@/components/notice-plans/NoticePlanShelf';

const api = vi.hoisted(() => ({ list: vi.fn(), highlights: vi.fn(), copy: vi.fn(), get: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  noticePlanApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

const PLAN_ID = '11111111-1111-4111-8111-111111111111';

function event(id: string, extra: Record<string, unknown> = {}) {
  return {
    feature_id: id,
    name: `축제 ${id}`,
    start_date: '2026-12-01',
    end_date: '2026-12-03',
    status: 'scheduled',
    venue_name: '경포호수광장',
    address: null,
    summary: '겨울 바다 불꽃',
    homepage_url: 'https://festival.example',
    lon: 128.9,
    lat: 37.8,
    marker_color: null,
    marker_icon: null,
    distance_m: 1234,
    ...extra,
  };
}

const highlights = {
  notice_plan_id: PLAN_ID,
  window_start: '2026-12-01',
  window_end: '2026-12-03',
  window_basis: 'plan',
  region_scope: 'sido',
  curated: [
    {
      feature_id: 'c1',
      name: '오죽헌',
      kind: 'place',
      category: '01020100',
      lon: 128.88,
      lat: 37.78,
      address: '강원 강릉시 율곡로3139번길 24',
      distance_m: 420,
      themes: [
        {
          theme_name: '한국관광 100선',
          collection_title: '한국관광 100선',
          edition_key: '2025-2026',
          summary: '율곡 이이가 태어난 곳',
          source_url: null,
        },
      ],
    },
  ],
  events: [event('e1'), event('e2'), event('e3'), event('e4', { lon: null, lat: null })],
  unavailable: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('formatters', () => {
  it('행사 기간과 거리를 짧게 표시한다', () => {
    expect(formatEventPeriod(null, null)).toBe('일정 미정');
    expect(formatEventPeriod('2026-12-01', '2026-12-01')).toBe('12월 1일');
    expect(formatEventPeriod('2026-12-01', '2026-12-03')).toBe('12월 1일 – 12월 3일');
    expect(formatNearDistance(null)).toBeNull();
    expect(formatNearDistance(420.4)).toBe('일정 장소에서 420m');
    expect(formatNearDistance(1234)).toBe('일정 장소에서 1.2km');
  });
});

describe('NoticePlanHighlights', () => {
  it('축제와 큐레이션을 보여주고 3건 넘는 목록은 접어 둔다', async () => {
    api.highlights.mockResolvedValue(highlights);
    const onAddPlace = vi.fn();
    render(<NoticePlanHighlights planId={PLAN_ID} onAddPlace={onAddPlace} />);

    const events = await screen.findByTestId('notice-plan-events');
    expect(within(events).getByText(/같은 시도/)).toBeInTheDocument();
    expect(within(events).getAllByRole('listitem')).toHaveLength(3);
    fireEvent.click(within(events).getByRole('button', { name: '1곳 더 보기' }));
    expect(within(events).getAllByRole('listitem')).toHaveLength(4);
    // 좌표 없는 행사는 여행에 넣을 수 없다 — 추가 버튼을 그리지 않는다.
    expect(within(events).queryByRole('button', { name: '축제 e4 내 여행에 추가' })).toBeNull();

    const curated = screen.getByTestId('notice-plan-curated');
    expect(within(curated).getByText('오죽헌')).toBeInTheDocument();
    expect(within(curated).getByText('한국관광 100선 2025-2026')).toBeInTheDocument();
    fireEvent.click(within(curated).getByRole('button', { name: '오죽헌 내 여행에 추가' }));
    expect(onAddPlace).toHaveBeenCalledWith(
      expect.objectContaining({ feature_id: 'c1', kind: 'place', lon: 128.88, lat: 37.78 }),
    );

    fireEvent.click(within(events).getByRole('button', { name: '축제 e1 내 여행에 추가' }));
    expect(onAddPlace).toHaveBeenLastCalledWith(
      expect.objectContaining({ feature_id: 'e1', kind: 'event', preferred_date: '2026-12-01' }),
    );
  });

  it('Map이 실패한 구역은 빈 목록과 구분해 안내한다', async () => {
    api.highlights.mockResolvedValue({
      ...highlights,
      curated: [],
      events: [],
      unavailable: ['events'],
      region_scope: 'nationwide',
    });
    render(<NoticePlanHighlights planId={PLAN_ID} onAddPlace={vi.fn()} />);
    const events = await screen.findByTestId('notice-plan-events');
    expect(within(events).getByText(/지금은 불러올 수 없습니다/)).toBeInTheDocument();
    expect(within(events).getByText(/전국/)).toBeInTheDocument();
    expect(
      within(screen.getByTestId('notice-plan-curated')).getByText('근처에 큐레이션 장소가 없습니다.'),
    ).toBeInTheDocument();
  });

  it('조회 실패 뒤 다시 시도할 수 있다', async () => {
    api.highlights.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(highlights);
    render(<NoticePlanHighlights planId={PLAN_ID} onAddPlace={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('주변 정보를 불러오지 못했습니다.');
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByTestId('notice-plan-events')).toBeInTheDocument();
    expect(api.highlights).toHaveBeenCalledTimes(2);
  });
});

describe('NoticePlanShelf 주변 정보 펼침', () => {
  it('펼칠 때만 주변 정보를 조회한다', async () => {
    api.list.mockResolvedValue([
      {
        notice_plan_id: PLAN_ID,
        slug: 'gangneung',
        title: '강릉 바다 코스',
        category: 'recommended',
        summary: null,
        source_name: null,
        destination: '강릉',
        starts_on: '2026-12-01',
        ends_on: '2026-12-03',
        is_published: true,
        version: 1,
        created_at: '2026-11-01T00:00:00Z',
        updated_at: '2026-11-01T00:00:00Z',
        pois: [],
      },
    ]);
    api.highlights.mockResolvedValue(highlights);
    render(<NoticePlanShelf />);
    const toggle = await screen.findByTestId(`notice-plan-highlights-toggle-${PLAN_ID}`);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(api.highlights).not.toHaveBeenCalled();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByTestId(`notice-plan-highlights-${PLAN_ID}`)).toBeInTheDocument();
    expect(api.highlights).toHaveBeenCalledWith(PLAN_ID, expect.anything());

    fireEvent.click(toggle);
    expect(screen.queryByTestId(`notice-plan-highlights-${PLAN_ID}`)).toBeNull();
  });
});
