import { useState } from 'react';
import { SvgUri } from 'react-native-svg';
import { makiIconName, makiIconUrl, markerGlyphName } from '@pinvi/domain';
import { Glyph } from './Glyph';

/**
 * 마커 아이콘 한 개(웹 `MakiIcon` 대응). 아이콘 고르기 목록의 이름은 앱에 묶인 lucide 그림, 목록 밖 이름
 * (카테고리가 준 maki 이름)은 maki SVG를 받아 그리고, 받지 못하면 기본 핀으로 대신한다.
 */
export function MarkerIcon({ icon, size, color }: { icon: string; size: number; color: string }) {
  const rendered = makiIconName(icon);
  const glyph = markerGlyphName(rendered);
  // 그림을 못 받은 maki 이름 — 이름이 바뀌면 다시 시도한다.
  const [failedIcon, setFailedIcon] = useState<string | null>(null);
  if (glyph) return <Glyph name={glyph} size={size} color={color} />;
  if (failedIcon === rendered) return <Glyph name="MapPin" size={size} color={color} />;
  return (
    <SvgUri
      uri={makiIconUrl(rendered)}
      width={size}
      height={size}
      fill={color}
      onError={() => setFailedIcon(rendered)}
    />
  );
}
