import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { TripWeatherCard, TripWeatherResolution } from '@pinvi/schemas';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';

const CARD_KEY = 'weather-card:seoul';

function foundWeather(): TripWeatherResolution {
  return {
    state: 'found',
    card_key: CARD_KEY,
  };
}

function weatherCards(): Record<typeof CARD_KEY, TripWeatherCard> {
  return {
    [CARD_KEY]: {
      asof: '2026-07-30T00:00:00+09:00',
      latest_at: '2026-07-30T15:00:00+09:00',
      is_stale: false,
      source_styles: ['observed', 'short'],
      metrics: [
        {
          forecast_style: 'observed',
          metric_key: 'T1H',
          metric_name: '기온',
          effective_at: '2026-07-29T15:00:00Z',
          observed_at: '2026-07-29T15:00:00Z',
          value_number: 24,
          unit: '℃',
        },
        {
          forecast_style: 'short',
          metric_key: 'TMP',
          metric_name: '기온',
          valid_from: '2026-07-30T09:00:00Z',
          value_number: 27,
          unit: '℃',
        },
        {
          forecast_style: 'short',
          metric_key: 'TMP',
          metric_name: '기온',
          issued_at: '2026-07-30T12:00:00+09:00',
          value_number: 99,
          unit: '℃',
        },
      ],
    },
  };
}

describe('TripWeatherSummary', () => {
  it('서버 batch의 found card를 별도 요청 없이 표시한다', () => {
    render(
      <TripWeatherSummary
        weather={foundWeather()}
        weatherCards={weatherCards()}
        date="2026-07-30"
      />,
    );

    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('현재');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('24℃');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('예보');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('27℃');
    expect(screen.getByTestId('trip-weather-summary')).not.toHaveTextContent('99℃');
  });

  it('T-366(ADR-068 게이트 G-2): 값의 출처(provider)를 국내/국외 구분 없이 표시한다', () => {
    const cardKey = 'weather-card:busan';
    render(
      <TripWeatherSummary
        weather={{ state: 'found', card_key: cardKey }}
        weatherCards={{
          [cardKey]: {
            asof: '2026-07-30T00:00:00+09:00',
            latest_at: '2026-07-30T15:00:00+09:00',
            is_stale: false,
            source_styles: ['observed'],
            metrics: [
              {
                forecast_style: 'observed',
                metric_key: 'T1H',
                metric_name: '기온',
                effective_at: '2026-07-30T09:00:00Z',
                value_number: 26,
                unit: '℃',
                provider: 'openweathermap',
              },
            ],
          },
        }}
        date="2026-07-30"
      />,
    );

    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('OpenWeatherMap');
  });

  it('found card에 해당 날짜 metric이 없으면 명시적인 no-data 상태를 표시한다', () => {
    render(
      <TripWeatherSummary
        weather={foundWeather()}
        weatherCards={weatherCards()}
        date="2026-09-30"
      />,
    );

    expect(screen.getByTestId('trip-weather-status')).toHaveTextContent(
      '이 날짜의 날씨 정보가 없습니다.',
    );
  });

  it.each([
    ['no_data', '이 날짜의 날씨 정보가 없습니다.'],
    ['retired', '장소 상태가 종료되어 날씨를 확인할 수 없습니다.'],
    ['suppressed', '비공개 장소는 날씨를 확인할 수 없습니다.'],
    ['missing', '장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.'],
    ['unavailable', '날씨 서비스를 일시적으로 사용할 수 없습니다.'],
  ] as const)('%s 상태를 구분해 표시한다', (state, message) => {
    render(<TripWeatherSummary weather={{ state }} date="2026-07-30" />);

    expect(screen.getByTestId('trip-weather-status')).toHaveTextContent(message);
  });

  it('ADR-077: 세 구간 요약(daily_summary)은 현재·예보와 섞지 않고 세 구간을 모두 보인다', () => {
    const cardKey = 'weather-card:daily';
    const slot = (bucket: string, hour: string, key: string, value: number, unit: string) => ({
      forecast_style: 'daily_summary',
      metric_key: key,
      metric_name: null,
      timeline_bucket: bucket,
      provider: 'python-kma-api',
      valid_at: `2026-10-20T${hour}:00:00+09:00`,
      value_number: value,
      unit,
    });
    render(
      <TripWeatherSummary
        weather={{ state: 'found', card_key: cardKey }}
        weatherCards={{
          [cardKey]: {
            asof: '2026-10-20T00:00:00+09:00',
            latest_at: '2026-10-21T09:00:00+09:00',
            is_stale: false,
            source_styles: ['daily_summary'],
            metrics: [
              slot('morning', '05', 'SLOT_TEMP_MIN', 8, 'deg_c'),
              slot('morning', '05', 'SLOT_TEMP_MAX', 14, 'deg_c'),
              slot('morning', '05', 'SLOT_HUMIDITY_AVG', 60, '%'),
              slot('noon', '11', 'SLOT_TEMP_MIN', 15, 'deg_c'),
              slot('noon', '11', 'SLOT_TEMP_MAX', 19.5, 'deg_c'),
              slot('noon', '11', 'SLOT_PRECIP_SUM', 1.5, 'mm'),
              slot('evening', '17', 'SLOT_TEMP_MIN', 11, 'deg_c'),
              slot('evening', '17', 'SLOT_TEMP_MAX', 16, 'deg_c'),
            ],
          },
        }}
        date="2026-10-20"
      />,
    );

    const summary = screen.getByTestId('trip-weather-summary');
    expect(summary).toHaveTextContent('시간대별');
    expect(summary).toHaveTextContent('아침 8~14°C 습도 60%');
    expect(summary).toHaveTextContent('점심 15~19.5°C 강수 1.5mm');
    expect(summary).toHaveTextContent('저녁 11~16°C');
    expect(summary).not.toHaveTextContent('현재');
    expect(summary).not.toHaveTextContent('예보');
  });
});

it('오래된 정보는 기온 한 값이 아닌 날씨 카드 전체 경고로 표시한다', () => {
  const cards = weatherCards();
  cards[CARD_KEY].is_stale = true;
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getByText('오래된 정보 포함')).toBeVisible();
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('24℃');
});

it('중기 요약은 두 제공자의 체감온도보다 실제 기온·하늘·강수 지표를 우선한다', () => {
  const cards = weatherCards();
  const metric = (key: string, value: number, provider = 'open_meteo', unit = 'deg_c') => ({
    metric_key: key,
    metric_name: null,
    forecast_style: 'mid',
    valid_at: '2026-07-30T09:00:00+09:00',
    provider,
    value_number: value,
    unit,
  });
  cards[CARD_KEY].metrics = [
    metric('FEELS_LIKE', 0.3, 'openweathermap'),
    metric('FEELS_LIKE', -5.4),
    metric('TMP', 12, 'python-kma-api'),
    metric('TMN', 8, 'python-kma-api'),
    metric('TMX', 15, 'python-kma-api'),
    metric('SKY', 3, 'python-kma-api', 'code'),
    metric('POP', 40, 'python-kma-api', '%'),
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  const summary = screen.getByTestId('trip-weather-summary');
  expect(summary).toHaveTextContent('기온 12°C');
  expect(summary).toHaveTextContent('최저 8°C');
  expect(summary).toHaveTextContent('최고 15°C');
  expect(summary).toHaveTextContent('하늘');
  expect(summary).toHaveTextContent('강수확률 40%');
  expect(summary).not.toHaveTextContent('FEELS_LIKE');
  expect(summary).not.toHaveTextContent('deg_c');
});

it('체감온도만 있는 원천도 정직한 라벨·단위로 표시하고 실제 기온을 지어내지 않는다', () => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'FEELS_LIKE',
      metric_name: null,
      forecast_style: 'mid',
      valid_at: '2026-07-30T09:00:00+09:00',
      provider: 'open_meteo',
      value_number: -5.4,
      unit: 'deg_c',
    },
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  const summary = screen.getByTestId('trip-weather-summary');
  expect(summary).toHaveTextContent('체감온도 -5.4°C');
  expect(summary).not.toHaveTextContent('기온');
  expect(summary).not.toHaveTextContent('FEELS_LIKE');
});

it('입력 행 순서가 바뀌어도 핵심 지표와 대표 provider 선택은 같다', () => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'FEELS_LIKE',
      forecast_style: 'mid',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: -5,
      unit: 'deg_c',
      provider: 'open_meteo',
    },
    {
      metric_key: 'TMP',
      forecast_style: 'mid',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: 99,
      unit: 'deg_c',
      provider: 'open_meteo',
    },
    {
      metric_key: 'TMP',
      forecast_style: 'mid',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: 12,
      unit: 'deg_c',
      provider: 'python-kma-api',
    },
    {
      metric_key: 'POP',
      forecast_style: 'mid',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: 40,
      unit: '%',
      provider: 'python-kma-api',
    },
  ];
  const view = render(
    <TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />,
  );
  const first = screen.getAllByTestId('weather-summary-metric').map((el) => el.textContent);
  expect(first).toEqual(['기온 12°C', '강수확률 40%', '체감온도 -5°C']);
  const reversed = {
    [CARD_KEY]: { ...cards[CARD_KEY], metrics: [...cards[CARD_KEY].metrics].reverse() },
  };
  view.rerender(
    <TripWeatherSummary weather={foundWeather()} weatherCards={reversed} date="2026-07-30" />,
  );
  expect(screen.getAllByTestId('weather-summary-metric').map((el) => el.textContent)).toEqual(
    first,
  );
});

it('관측은 최신·예보는 가장 이른 대표 시각을 고르며 평균이나 범위를 지어내지 않는다', () => {
  const cards = weatherCards();
  const metric = (style: string, hour: string, value: number) => ({
    metric_key: style === 'observed' ? 'T1H' : 'TMP',
    forecast_style: style,
    valid_at: '2026-07-30T' + hour + ':00:00+09:00',
    value_number: value,
    unit: 'deg_c',
  });
  cards[CARD_KEY].metrics = [
    metric('observed', '09', 1),
    metric('observed', '12', 2),
    metric('mid', '12', 4),
    metric('mid', '09', 3),
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getAllByTestId('weather-summary-metric').map((el) => el.textContent)).toEqual([
    '기온 2°C',
    '기온 3°C',
  ]);
});

it('서로 다른 단위·시간 누적 강수와 0·빈 설명을 손실 없이 표시한다', () => {
  const cards = weatherCards();
  const metric = (key: string, value: number, unit: string | null) => ({
    metric_key: key,
    forecast_style: 'short',
    valid_at: '2026-07-30T09:00:00+09:00',
    value_number: value,
    value_text: '',
    unit,
  });
  cards[CARD_KEY].metrics = [
    metric('TMP', 0, 'deg_c'),
    metric('TMP', 32, 'deg_f'),
    metric('RN1', 1, 'mm'),
    metric('PCP', 2, 'mm'),
    metric('POP', 0, null),
    metric('WEATHER_CODE', 800, 'code'),
    metric('SKY', 3, 'code'),
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  const summary = screen.getByTestId('trip-weather-summary');
  expect(summary).toHaveTextContent('기온 0°C');
  expect(summary).toHaveTextContent('기온 32°F');
  expect(summary).toHaveTextContent('1시간 강수량 1mm');
  expect(summary).toHaveTextContent('강수량 2mm');
  expect(summary).toHaveTextContent('강수확률 0');
  expect(summary).not.toHaveTextContent('강수확률 0%');
  expect(summary).toHaveTextContent('날씨 코드 800');
  expect(summary).toHaveTextContent('하늘 3');
});

it('미세먼지는 관측·예보가 섞여도 입력 순서와 무관하게 관측을 먼저 고른다', () => {
  const cards = weatherCards();
  const metrics = [
    {
      metric_key: 'PM10',
      forecast_style: 'observed',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: 10,
      unit: 'ug/m3',
      provider: 'python-airkorea-api',
    },
    {
      metric_key: 'PM10',
      forecast_style: 'short',
      valid_at: '2026-07-30T18:00:00+09:00',
      value_number: 90,
      unit: 'ug/m3',
      provider: 'python-airkorea-api',
    },
  ];
  cards[CARD_KEY].metrics = metrics;
  const view = render(
    <TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />,
  );
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('미세 10μg/m³');
  view.rerender(
    <TripWeatherSummary
      weather={foundWeather()}
      weatherCards={{ [CARD_KEY]: { ...cards[CARD_KEY], metrics: [...metrics].reverse() } }}
      date="2026-07-30"
    />,
  );
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('미세 10μg/m³');
  expect(screen.getByTestId('trip-weather-summary')).not.toHaveTextContent('90μg/m³');
});

it('표시 기호가 없는 code·index·단위 미확인 사실은 서로 병합하지 않는다', () => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = ['code', 'index', null].map((unit, i) => ({
    metric_key: 'WEATHER_CODE',
    forecast_style: 'mid',
    valid_at: '2026-07-30T09:00:00+09:00',
    value_number: i + 1,
    unit,
  }));
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getAllByTestId('weather-summary-metric')).toHaveLength(3);
});

it.each([0, 2])('이름 없는 현재 RN1도 %smm 실제값을 표시한다', (value) => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'RN1',
      metric_name: null,
      forecast_style: 'observed',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: value,
      unit: 'mm',
    },
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent(
    '1시간 강수량 ' + value + 'mm',
  );
});

it.each([
  [1, '맑음'],
  [2, '구름조금'],
  [3, '구름많음'],
  [4, '흐림'],
] as const)('기상청 SKY 코드 %s는 정본 설명 %s로 표시한다', (code, label) => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'SKY',
      forecast_style: 'mid',
      provider: 'python-kma-api',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: code,
      unit: 'code',
    },
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('하늘 ' + label);
});

it('제공자가 다른 SKY나 WEATHER_CODE는 기상청 코드로 바꾸지 않는다', () => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = ['SKY', 'WEATHER_CODE'].map((key) => ({
    metric_key: key,
    forecast_style: 'mid',
    provider: 'open_meteo',
    valid_at: '2026-07-30T09:00:00+09:00',
    value_number: 3,
    unit: 'code',
  }));
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  const summary = screen.getByTestId('trip-weather-summary');
  expect(summary).toHaveTextContent('하늘 3');
  expect(summary).toHaveTextContent('날씨 코드 3');
  expect(summary).not.toHaveTextContent('구름많음');
});

it.each([
  ['1', '맑음'],
  ['2', '구름조금'],
  ['3', '구름많음'],
  ['4', '흐림'],
] as const)('기상청 문자열 SKY 코드 %s도 설명 %s로 표시한다', (code, label) => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'SKY',
      forecast_style: 'mid',
      provider: 'python-kma-api',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: null,
      value_text: code,
      unit: 'code',
    },
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('하늘 ' + label);
});

it.each(['원천 설명', '9'])('기상청 SKY의 실제 설명·미등록 문자열 %s는 보존한다', (text) => {
  const cards = weatherCards();
  cards[CARD_KEY].metrics = [
    {
      metric_key: 'SKY',
      forecast_style: 'mid',
      provider: 'python-kma-api',
      valid_at: '2026-07-30T09:00:00+09:00',
      value_number: 3,
      value_text: text,
      unit: 'code',
    },
  ];
  render(<TripWeatherSummary weather={foundWeather()} weatherCards={cards} date="2026-07-30" />);
  expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('하늘 ' + text);
  expect(screen.getByTestId('trip-weather-summary')).not.toHaveTextContent('구름많음');
});
