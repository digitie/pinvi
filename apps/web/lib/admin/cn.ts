import { type ClassValue, clsx } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/**
 * Admin 전용 className 병합 — kor-travel-map admin의 `cn`과 같은 역할(T-356).
 *
 * KTM은 표준 `twMerge(clsx(...))`를 그대로 쓰지만, 그건 KTM의 커스텀 유틸이 tailwind-merge의
 * 기본 그룹 추론에 우연히 잘 맞아떨어지기 때문이다. pinvi는 preset이 소유한 이름과 admin `@theme`가
 * 소유한 이름이 섞여 있어 추론이 어긋나는 지점이 실제로 있다:
 *
 * - `rounded-control`/`rounded-panel` vs preset의 `rounded-sm|md|lg|xl` — 같은 border-radius 축이라
 *   뒤에 온 쪽이 이겨야 한다. tailwind-merge는 임의 커스텀 이름을 radius 그룹으로 알지 못한다.
 * - `h-control`/`h-control-sm` vs `h-9`/`h-10` — 같은 height 축.
 * - `text-2xs`/`text-md` vs `text-xs|sm|lg` — font-size 축. 특히 `text-*`는 색 축과 이름이 겹쳐
 *   (`text-ink`) 잘못 묶이면 색이 조용히 사라진다.
 *
 * 그래서 그룹을 명시 등록한다. 이 파일이 admin 컴포넌트의 variant 병합 정확도를 책임진다.
 */
export const cn = (() => {
  const twMerge = extendTailwindMerge({
    extend: {
      classGroups: {
        rounded: [{ rounded: ['control', 'panel'] }],
        h: [{ h: ['control', 'control-sm'] }],
        w: [{ w: ['rail'] }],
        'font-size': [{ text: ['2xs', 'md'] }],
      },
    },
  });
  return (...inputs: ClassValue[]) => twMerge(clsx(inputs));
})();
