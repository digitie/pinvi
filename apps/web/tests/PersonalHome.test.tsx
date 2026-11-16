import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { PersonalHome, nextTripBadge } from '@/components/home/PersonalHome';
import type { UserHome } from '@pinvi/schemas';

const api = vi.hoisted(() => ({ getHome: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  userApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
vi.mock('next/link', () => ({
  default: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props} />
  ),
}));

const trip = {
  trip_id: '11111111-1111-4111-8111-111111111111',
  title: '다음 제주',
  region_hint: '제주',
  region_name: '제주',
  start_date: '2026-11-21',
  end_date: '2026-11-22',
  phase: 'upcoming' as const,
  days_until: 5,
  place_count: 3,
};

const home: UserHome = {
  today: '2026-11-16',
  stats: {
    trip_count: 4,
    upcoming_trip_count: 1,
    ongoing_trip_count: 0,
    completed_trip_count: 2,
    undated_trip_count: 1,
    travel_day_count: 5,
    visited_place_count: 7,
    region_count: 2,
  },
  next_trip: trip,
  upcoming_trips: [
    {
      ...trip,
      trip_id: '44444444-4444-4444-8444-444444444444',
      title: '언젠가',
      start_date: null,
      end_date: null,
      phase: 'undated',
      days_until: null,
      place_count: 0,
      region_name: null,
      region_hint: null,
    },
  ],
  recent_trips: [
    {
      ...trip,
      trip_id: '33333333-3333-4333-8333-333333333333',
      title: '지난 강릉',
      region_name: '강원',
      start_date: '2026-11-01',
      end_date: '2026-11-02',
      phase: 'completed',
      days_until: null,
      place_count: 4,
    },
  ],
  recent_places: [
    {
      poi_id: '22222222-2222-4222-8222-222222222222',
      trip_id: '33333333-3333-4333-8333-333333333333',
      trip_title: '지난 강릉',
      name: '경포해변',
      category: null,
      visited_on: '2026-11-01',
      region_name: '강원',
    },
  ],
  regions: [
    { code: '51', name: '강원', place_count: 4, trip_count: 1 },
    { code: '11', name: '서울', place_count: 0, trip_count: 1 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('개인 홈', () => {
  it('다음 여행·통계·지역·최근 여행·최근 장소를 보여준다', async () => {
    api.getHome.mockResolvedValue(home);
    render(<PersonalHome />);
    const next = await screen.findByTestId('home-next-trip');
    expect(next).toHaveTextContent('다음 제주');
    expect(within(next).getByRole('link')).toHaveAttribute('href', `/trips/${trip.trip_id}`);
    expect(screen.getByTestId('home-next-trip-badge')).toHaveTextContent('D-5');
    expect(screen.getByTestId('home-stat-trips')).toHaveTextContent('다녀온 여행2번');
    expect(screen.getByTestId('home-stat-days')).toHaveTextContent('여행한 날5일');
    expect(screen.getByTestId('home-stat-places')).toHaveTextContent('다녀온 장소7곳');
    expect(screen.getByTestId('home-stat-regions')).toHaveTextContent('다녀온 지역2/17');
    expect(screen.getByTestId('home-stat-summary')).toHaveTextContent(
      '전체 여행 4개 · 예정 1개 · 날짜 미정 1개',
    );
    const regions = screen.getByTestId('home-regions');
    expect(regions).toHaveTextContent('강원4곳');
    // 장소 근거 없이 여행 지역만 있는 시도는 여행 수로 보인다.
    expect(regions).toHaveTextContent('서울여행 1');
    expect(screen.getByTestId('home-upcoming')).toHaveTextContent('날짜 미정');
    expect(screen.getByTestId('home-recent')).toHaveTextContent('지난 강릉');
    expect(screen.getByTestId('home-recent')).toHaveTextContent('장소 4곳');
    expect(screen.getByTestId('home-places')).toHaveTextContent('경포해변');
    expect(screen.getByTestId('home-places')).toHaveTextContent('강원 · 지난 강릉');
  });

  it('여행이 없으면 첫 여행 만들기를 안내하고 빈 목록은 그리지 않는다', async () => {
    api.getHome.mockResolvedValue({
      ...home,
      stats: {
        ...home.stats,
        trip_count: 0,
        completed_trip_count: 0,
        upcoming_trip_count: 0,
        undated_trip_count: 0,
        travel_day_count: 0,
        visited_place_count: 0,
        region_count: 0,
      },
      next_trip: null,
      upcoming_trips: [],
      recent_trips: [],
      recent_places: [],
      regions: [],
    });
    render(<PersonalHome />);
    const empty = await screen.findByTestId('home-next-trip-empty');
    expect(empty).toHaveTextContent('아직 여행이 없습니다.');
    expect(within(empty).getByRole('link', { name: '새 여행 만들기' })).toHaveAttribute(
      'href',
      '/trips',
    );
    expect(screen.queryByTestId('home-recent')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-places')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-regions')).not.toBeInTheDocument();
  });

  it('불러오기 실패는 원인과 다시 시도를 보여주고 재시도로 회복한다', async () => {
    api.getHome.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(home);
    render(<PersonalHome />);
    expect(await screen.findByRole('alert')).toHaveTextContent('홈을 불러오지 못했습니다.');
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByTestId('home-next-trip')).toHaveTextContent('다음 제주');
  });
});

describe('nextTripBadge', () => {
  it('진행 중·오늘 출발·D-n을 구분한다', () => {
    expect(nextTripBadge({ phase: 'ongoing', days_until: null })).toBe('여행 중');
    expect(nextTripBadge({ phase: 'upcoming', days_until: 0 })).toBe('오늘 출발');
    expect(nextTripBadge({ phase: 'upcoming', days_until: 12 })).toBe('D-12');
    expect(nextTripBadge({ phase: 'undated', days_until: null })).toBeNull();
  });
});
