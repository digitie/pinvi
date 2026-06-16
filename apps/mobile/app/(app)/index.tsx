import { Pressable, View } from 'react-native';
import { useRouter, type Href } from 'expo-router';
import { useAuth } from '../../lib/auth';
import { Body, Heading, Muted, Screen, Subheading } from '../../components/ui';

/**
 * 홈(`/`) — 인증 후 진입점. 주요 화면으로의 네비게이션 타일.
 * 지도(§4)는 `maplibre-vworld-react` 선결(이슈 #2/#3) 전까지 placeholder.
 */
const TILES: { href: Href; title: string; description: string }[] = [
  { href: '/trips', title: '내 여행', description: '여행 계획을 보고 편집' },
  { href: '/notice-plans', title: '추천 여행', description: '큐레이션 일정 둘러보기' },
  { href: '/map', title: '지도', description: '주변 장소 탐색' },
  { href: '/settings', title: '설정', description: '알림·동의·토큰' },
  { href: '/profile', title: '프로필', description: '계정·소셜 연결' },
];

export default function HomeScreen() {
  const router = useRouter();
  const { user, offline } = useAuth();

  return (
    <Screen>
      <View className="gap-6 py-2">
        <View className="gap-1">
          <Heading>안녕하세요{user?.nickname ? `, ${user.nickname}님` : ''}</Heading>
          <Body>오늘은 어떤 여행을 준비할까요?</Body>
          {offline ? <Muted>오프라인 — 저장된 정보로 표시 중</Muted> : null}
        </View>

        <View className="gap-3">
          {TILES.map((tile) => (
            <Pressable
              key={String(tile.href)}
              accessibilityRole="button"
              onPress={() => router.push(tile.href)}
              className="rounded-md border border-hairline-soft bg-canvas p-4 active:opacity-80"
            >
              <Subheading>{tile.title}</Subheading>
              <Muted>{tile.description}</Muted>
            </Pressable>
          ))}
        </View>
      </View>
    </Screen>
  );
}
