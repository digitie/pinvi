import { describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { FeatureDetailCard, SourceIntroduction as Intro } from '@pinvi/schemas';
import { FeatureDetailCardBody } from '@/components/map/FeatureDetailCardBody';
import { SourceIntroduction } from '@/components/map/SourceIntroduction';

const IMAGE = 'https://tong.visitkorea.or.kr/cms/resource/29/3488229_image2_1.jpg';
const T = 'intro';

const TYPE3 = {
  kogl_type: 3,
  no_derivatives: true,
  license_label: '공공누리 제3유형: 출처표시 + 변경금지',
  license_url: 'https://www.kogl.or.kr/info/licenseType3.do',
} as const;
const TYPE1 = {
  kogl_type: 1,
  no_derivatives: false,
  license_label: '공공누리 제1유형: 출처표시',
  license_url: 'https://www.kogl.or.kr/info/licenseType1.do',
} as const;

function intro(over: Partial<Intro> = {}): Intro {
  return {
    provider: 'tourapi',
    attribution: '한국관광공사',
    reference_date: null,
    overview: '괴산호를 따라 이어진 옛길이다.',
    images: [{ url: IMAGE, alt: '산막이옛길 대표 사진', ...TYPE3 }],
    kogl_type: null,
    license_label: null,
    license_url: null,
    ...over,
  };
}

describe('SourceIntroduction', () => {
  it('원본 이미지를 크롭 없이(object-contain) 보이고 원본 URL로 연결한다', () => {
    render(<SourceIntroduction introduction={intro()} testId={T} />);
    const img = screen.getByTestId(`${T}-image`);
    expect(img).toHaveAttribute('src', IMAGE);
    expect(img).toHaveAttribute('alt', '산막이옛길 대표 사진');
    expect(img).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(img.className).toContain('object-contain');
    expect(img.className).not.toContain('object-cover');
    expect(img).toHaveAttribute('data-no-derivatives', 'true');
    const link = screen.getByTestId(`${T}-image-link`);
    expect(link).toHaveAttribute('href', IMAGE);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAccessibleName('산막이옛길 대표 사진 — 원본 이미지 새 창으로 보기');
  });

  it('출처와 공공누리 유형을 링크와 함께 표시한다', () => {
    render(<SourceIntroduction introduction={intro()} testId={T} />);
    const line = screen.getByTestId(`${T}-attribution`);
    expect(line).toHaveTextContent('출처: 한국관광공사');
    // 공공누리 유형은 이미지에 걸린 조건이라 그 이미지 바로 아래에 붙는다.
    const license = within(screen.getByTestId(`${T}-figure`)).getByTestId(`${T}-license`);
    expect(license).toHaveTextContent('공공누리 제3유형: 출처표시 + 변경금지');
    expect(license).toHaveAttribute('href', 'https://www.kogl.or.kr/info/licenseType3.do');
    expect(license).toHaveAttribute('data-kogl-type', '3');
  });

  it('소개문의 HTML 꼴 문자열을 해석하지 않고 텍스트로 그린다', () => {
    const { container } = render(
      <SourceIntroduction
        introduction={intro({ overview: '<img src=x onerror="alert(1)">옛길', images: [] })}
        testId={T}
      />,
    );
    expect(screen.getByTestId(`${T}-overview`)).toHaveTextContent(
      '<img src=x onerror="alert(1)">옛길',
    );
    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('짧은 소개문은 접기 버튼이 없다', () => {
    render(<SourceIntroduction introduction={intro()} testId={T} />);
    expect(screen.queryByTestId(`${T}-overview-toggle`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`${T}-overview`).className).not.toContain('line-clamp');
  });

  it('긴 소개문은 접어 두고 더 보기로 펼친다(aria-expanded·aria-controls)', () => {
    render(<SourceIntroduction introduction={intro({ overview: '가'.repeat(300) })} testId={T} />);
    const overview = screen.getByTestId(`${T}-overview`);
    const toggle = screen.getByTestId(`${T}-overview-toggle`);
    expect(overview.className).toContain('line-clamp-4');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls', overview.id);
    expect(toggle).toHaveTextContent('소개 더 보기');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent('소개 접기');
    expect(overview.className).not.toContain('line-clamp');
  });

  it('줄 수가 많으면 짧아도 접는다', () => {
    render(<SourceIntroduction introduction={intro({ overview: '1\n2\n3\n4\n5' })} testId={T} />);
    expect(screen.getByTestId(`${T}-overview-toggle`)).toBeInTheDocument();
  });

  it('이미지 없이 소개문만 있으면 공공누리 표시 없이 출처만 단다', () => {
    render(<SourceIntroduction introduction={intro({ images: [] })} testId={T} />);
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent('출처: 한국관광공사');
    expect(screen.queryByTestId(`${T}-license`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`${T}-image`)).not.toBeInTheDocument();
  });

  it('이미지를 불러오지 못하면 틀을 남기지 않고, 소개문이 없으면 블록째 숨긴다', () => {
    render(<SourceIntroduction introduction={intro({ overview: null })} testId={T} />);
    fireEvent.error(screen.getByTestId(`${T}-image`));
    expect(screen.queryByTestId(T)).not.toBeInTheDocument();
  });

  it('허용 밖 이미지 호스트·공공누리 링크는 화면에서도 거른다(서버 검증과 이중)', () => {
    render(
      <SourceIntroduction
        introduction={intro({
          images: [{ url: 'https://evil.example/a.jpg', alt: 'x', ...TYPE1 }],
        })}
        testId={T}
      />,
    );
    expect(screen.queryByTestId(`${T}-image`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`${T}-license`)).not.toBeInTheDocument();
    cleanup();
    render(
      <SourceIntroduction
        introduction={intro({
          images: [{ url: IMAGE, alt: 'x', ...TYPE3, license_url: 'javascript:alert(1)' }],
        })}
        testId={T}
      />,
    );
    // 공공누리 링크가 이상한 이미지는 조건을 보일 수 없으니 이미지째 뺀다.
    expect(screen.queryByTestId(`${T}-image`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`${T}-license`)).not.toBeInTheDocument();
    cleanup();
    render(
      <SourceIntroduction
        introduction={intro({
          provider: 'krheritage',
          attribution: '국가유산청, www.khs.go.kr',
          images: [{ url: IMAGE, alt: 'x', ...TYPE1 }],
        })}
        testId={T}
      />,
    );
    // 이미지 허용 호스트가 없는 원천(국가유산)은 이미지를 그리지 않는다.
    expect(screen.queryByTestId(`${T}-image`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent(
      '출처: 국가유산청, www.khs.go.kr',
    );
  });

  it('이미지 틀은 고정 높이이고 모서리를 깎지 않는다(변경금지 — 원본 그대로)', () => {
    render(<SourceIntroduction introduction={intro()} testId={T} />);
    const link = screen.getByTestId(`${T}-image-link`);
    expect(link.className).toContain('h-56');
    expect(link.className).not.toMatch(/rounded|overflow-hidden/);
  });

  it('이미지가 깨지면 공공누리 표시도 뺀다(소개문은 남는다)', () => {
    render(<SourceIntroduction introduction={intro()} testId={T} />);
    fireEvent.error(screen.getByTestId(`${T}-image`));
    expect(screen.queryByTestId(`${T}-image-link`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`${T}-overview`)).toBeInTheDocument();
    expect(screen.queryByTestId(`${T}-license`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent('출처: 한국관광공사');
  });
});

describe('SourceIntroduction — 갤러리', () => {
  const SECOND = 'https://tong.visitkorea.or.kr/cms/resource/02/2_image2_1.jpg';
  const gallery = () =>
    intro({
      images: [
        { url: IMAGE, alt: '산막이옛길 대표 사진', ...TYPE3 },
        { url: SECOND, alt: '산막이옛길 출렁다리', ...TYPE1 },
      ],
    });

  it('여러 장이면 가로 갤러리로, 이미지마다 공공누리 유형을 붙인다', () => {
    render(<SourceIntroduction introduction={gallery()} testId={T} />);
    const list = screen.getByTestId(`${T}-gallery`);
    expect(list).toHaveAccessibleName('사진 2장');
    expect(list.className).toContain('overflow-x-auto');
    const figures = within(list).getAllByTestId(`${T}-figure`);
    expect(figures).toHaveLength(2);
    const [first, second] = figures as [HTMLElement, HTMLElement];
    expect(within(first).getByTestId(`${T}-license`)).toHaveAttribute('data-kogl-type', '3');
    expect(within(first).getByTestId(`${T}-image`)).toHaveAttribute('data-no-derivatives', 'true');
    expect(within(second).getByTestId(`${T}-license`)).toHaveTextContent(
      '공공누리 제1유형: 출처표시',
    );
    expect(within(second).getByTestId(`${T}-license`)).toHaveAttribute(
      'href',
      'https://www.kogl.or.kr/info/licenseType1.do',
    );
    for (const img of within(list).getAllByTestId(`${T}-image`)) {
      expect(img).toHaveAttribute('loading', 'lazy');
      expect(img.className).toContain('object-contain');
      expect(img.className).not.toContain('object-cover');
    }
  });

  it('갤러리 이미지 하나가 깨지면 그 이미지와 공공누리 표시만 빠지고 갤러리 틀은 그대로다', () => {
    render(<SourceIntroduction introduction={gallery()} testId={T} />);
    fireEvent.error(screen.getAllByTestId(`${T}-image`)[1]!);
    expect(screen.getByTestId(`${T}-gallery`)).toBeInTheDocument();
    expect(screen.getAllByTestId(`${T}-image`)).toHaveLength(1);
    expect(screen.getAllByTestId(`${T}-license`)).toHaveLength(1);
  });

  it('기준일이 있으면 출처 줄에 함께 적는다', () => {
    render(
      <SourceIntroduction
        introduction={intro({
          provider: 'datagokr_museum',
          attribution: '공공데이터포털 전국박물관미술관정보표준데이터',
          reference_date: '2026-05-31',
          images: [],
        })}
        testId={T}
      />,
    );
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent(
      '출처: 공공데이터포털 전국박물관미술관정보표준데이터 · 기준일 2026-05-31',
    );
  });
});

describe('FeatureDetailCardBody — 출처 소개', () => {
  function placeCard(introduction: Intro | null) {
    return {
      kind: 'place',
      feature_id: '01a1c43c-f414-77d4-8e4e-addb3b650f56',
      name: '산막이옛길',
      coord: { lon: 127.87, lat: 36.76 },
      category: '01080500',
      category_label: '트레킹',
      address_line: '충북 괴산군 칠성면 산막이옛길 88',
      marker_color: 'P-02',
      marker_icon: 'attraction',
      homepage_url: null,
      enrichment: [],
      degraded_providers: [],
      containing_areas: [],
      phone: null,
      business_hours: null,
      introduction,
      visit_guide: null,
    } as Extract<FeatureDetailCard, { kind: 'place' }>;
  }

  it('place 카드에 소개 블록을 그린다', () => {
    render(<FeatureDetailCardBody card={placeCard(intro())} />);
    const block = screen.getByTestId('feature-detail-card-body-introduction');
    expect(within(block).getByTestId('feature-detail-card-body-introduction-image')).toBeVisible();
    expect(block).toHaveTextContent('출처: 한국관광공사');
  });

  it('축제(event) 카드도 소개 블록을 그린다', () => {
    const card: Extract<FeatureDetailCard, { kind: 'event' }> = {
      ...placeCard(null),
      kind: 'event',
      start_date: '2026-04-01',
      end_date: '2026-04-10',
      venue: null,
      introduction: intro({ overview: '벚꽃 축제' }),
      visit_guide: null,
    };
    render(<FeatureDetailCardBody card={card} />);
    expect(screen.getByTestId('feature-detail-card-body-introduction')).toHaveTextContent(
      '벚꽃 축제',
    );
  });

  it('소개가 없으면 빈 블록을 만들지 않는다', () => {
    render(<FeatureDetailCardBody card={placeCard(null)} />);
    expect(screen.queryByTestId('feature-detail-card-body-introduction')).not.toBeInTheDocument();
  });
});
