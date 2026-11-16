/**
 * 마커 아이콘 이름 → 앱에 묶인 lucide 그림(`components/map/MakiIcon.tsx`가 그린다).
 */
import { makiIconName } from '@/lib/makiIcons';
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

/**
 * 아이콘 고르기 목록(`MARKER_ICON_OPTIONS`)의 이름은 앱에 묶인 lucide 그림으로 그린다 — 외부 CDN
 * 없이 바로 그려지고, 고르기 칩과 지도 마커가 같은 그림이다. 목록 밖 이름(카테고리가 준 maki 이름)은
 * 예전처럼 maki SVG를 받아 그린다.
 */
const BUNDLED_ICONS: Record<string, LucideIcon> = {
  marker: MapPin,
  star: Star,
  heart: Heart,
  home: House,
  lodging: BedDouble,
  campsite: Tent,
  restaurant: UtensilsCrossed,
  cafe: Coffee,
  bakery: Croissant,
  bar: Beer,
  shop: ShoppingBag,
  grocery: ShoppingCart,
  attraction: Sparkles,
  viewpoint: Camera,
  museum: Landmark,
  monument: Landmark,
  castle: Castle,
  'religious-buddhist': Flower2,
  park: Trees,
  mountain: Mountain,
  beach: Umbrella,
  swimming: Waves,
  'amusement-park': FerrisWheel,
  zoo: PawPrint,
  aquarium: Fish,
  theatre: Drama,
  golf: Flag,
  bicycle: Bike,
  parking: SquareParking,
  fuel: Fuel,
  car: Car,
  bus: Bus,
  rail: TrainFront,
  airport: Plane,
  ferry: Ship,
  hospital: Hospital,
};

export function hasBundledIcon(icon: string): boolean {
  return makiIconName(icon) in BUNDLED_ICONS;
}

/** maki 이름(별칭 적용 뒤)에 해당하는 묶인 아이콘. 없으면 null(maki SVG를 받아 그린다). */
export function bundledMarkerIcon(renderedIcon: string): LucideIcon | null {
  return BUNDLED_ICONS[renderedIcon] ?? null;
}
