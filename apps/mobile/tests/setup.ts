import type { ReactNode } from 'react';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// 화면 크기 — react-native-web `Dimensions`는 documentElement 크기를 읽는데 jsdom은 0이다. 폰 크기로 둔다.
Object.defineProperty(document.documentElement, 'clientWidth', { configurable: true, value: 390 });
Object.defineProperty(document.documentElement, 'clientHeight', { configurable: true, value: 844 });

// globals를 켜지 않으므로 RTL 자동 cleanup이 걸리지 않는다 — 테스트마다 직접 비운다.
afterEach(() => {
  cleanup();
});

// node_modules 패키지는 alias를 거치지 않고 Node가 읽어 진짜 `react-native`(Flow 소스)를 부른다.
// 화면 껍데기(SafeAreaView)만 쓰므로 react-native-web View로 대신한다.
vi.mock('react-native-safe-area-context', async () => {
  const { View } = await import('react-native');
  return {
    SafeAreaView: View,
    SafeAreaProvider: ({ children }: { children?: ReactNode }) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

// lucide-react-native·react-native-svg도 진짜 `react-native`를 부른다 — 그림 대신 이름을 남기는 표식으로
// 바꾼다. 표에 없는 그림을 앱이 부르면 "No export defined" 오류로 드러난다(그림 표가 공용 이름과 어긋나지 않게).
vi.mock('lucide-react-native', async () => {
  const { createElement } = await import('react');
  const { MARKER_ICON_GLYPHS, WEATHER_GLYPH_NAMES } = await import('@pinvi/domain');
  const names = new Set<string>([...Object.values(MARKER_ICON_GLYPHS), ...WEATHER_GLYPH_NAMES]);
  return Object.fromEntries(
    [...names].map((name) => [
      name,
      (props: { color?: string; size?: number }) =>
        createElement('span', {
          'data-lucide': name,
          'data-color': props.color,
          'data-size': props.size,
        }),
    ]),
  );
});

vi.mock('react-native-svg', async () => {
  const { createElement } = await import('react');
  return {
    SvgUri: (props: { uri: string; fill?: string }) =>
      createElement('span', { 'data-svg-uri': props.uri, 'data-fill': props.fill }),
  };
});
