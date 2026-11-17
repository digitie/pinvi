/**
 * 마커 아이콘 이름 → 앱에 묶인 lucide 그림(`components/map/MakiIcon.tsx`가 그린다).
 * 어떤 이름을 어떤 그림으로 그릴지는 `@pinvi/domain` `MARKER_ICON_GLYPHS`가 정본이다(모바일과 공용).
 */
import { makiIconName, markerGlyphName, type MarkerGlyphName } from '@pinvi/domain';
import {
  Flower2,
  Beer,
  BedDouble,
  Bike,
  Bus,
  Camera,
  Car,
  Castle,
  Coffee,
  Croissant,
  Drama,
  FerrisWheel,
  Fish,
  Flag,
  Fuel,
  Heart,
  Hospital,
  House,
  Landmark,
  MapPin,
  Mountain,
  PawPrint,
  Plane,
  Ship,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  SquareParking,
  Star,
  Tent,
  TrainFront,
  Trees,
  Umbrella,
  UtensilsCrossed,
  Waves,
  type LucideIcon,
} from 'lucide-react';

/** 공용 그림 이름 → lucide-react 컴포넌트. 이름이 빠지면 타입 오류다. */
const GLYPHS: Record<MarkerGlyphName, LucideIcon> = {
  MapPin,
  Star,
  Heart,
  House,
  BedDouble,
  Tent,
  UtensilsCrossed,
  Coffee,
  Croissant,
  Beer,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  Camera,
  Landmark,
  Castle,
  Flower2,
  Trees,
  Mountain,
  Umbrella,
  Waves,
  FerrisWheel,
  PawPrint,
  Fish,
  Drama,
  Flag,
  Bike,
  SquareParking,
  Fuel,
  Car,
  Bus,
  TrainFront,
  Plane,
  Ship,
  Hospital,
};

export function hasBundledIcon(icon: string): boolean {
  return markerGlyphName(makiIconName(icon)) != null;
}

/** maki 이름(별칭 적용 뒤)에 해당하는 묶인 아이콘. 없으면 null(maki SVG를 받아 그린다). */
export function bundledMarkerIcon(renderedIcon: string): LucideIcon | null {
  const name = markerGlyphName(renderedIcon);
  return name ? GLYPHS[name] : null;
}
