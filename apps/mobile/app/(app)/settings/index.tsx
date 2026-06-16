import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { useRouter, type Href } from 'expo-router';
import { useAuth } from '../../../lib/auth';
import { mobileConfig } from '../../../lib/config';
import { Button, Card, Heading, Muted, Screen, Subheading } from '../../../components/ui';

const LINKS: { href: Href; title: string; description: string }[] = [
  { href: '/profile', title: '계정', description: '프로필·소셜 연결' },
  { href: '/settings/telegram', title: 'Telegram 알림', description: '알림 받을 chat 연결' },
  { href: '/settings/consents', title: '동의 관리', description: '동의 현황·선택 항목 철회' },
  { href: '/settings/mcp-tokens', title: 'MCP 토큰', description: '토큰 발급·회수' },
];

/**
 * 설정 — 웹 `(app)/settings/*` 대응 허브. 계정/프로필 + 후속 항목(텔레그램·동의·MCP 토큰).
 * 세부 설정 화면은 후속(expo-implementation-plan §2). 여기서는 진입 + 로그아웃.
 */
export default function SettingsScreen() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);

  const onLogout = async () => {
    setBusy(true);
    try {
      await logout();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <View className="gap-5 py-2">
        <Heading>설정</Heading>

        <View className="gap-3">
          {LINKS.map((link) => (
            <Pressable
              key={String(link.href)}
              accessibilityRole="button"
              onPress={() => router.push(link.href)}
              className="rounded-md border border-hairline-soft bg-canvas p-4 active:opacity-80"
            >
              <Subheading>{link.title}</Subheading>
              <Muted>
                {link.href === '/profile' ? (user?.email ?? link.description) : link.description}
              </Muted>
            </Pressable>
          ))}
        </View>

        <Card className="gap-1">
          <Subheading>앱 정보</Subheading>
          <Muted>API: {mobileConfig.apiBaseUrl}</Muted>
          <Muted>지도 키: 서버 발급(번들 안 함)</Muted>
        </Card>

        <Button label="로그아웃" variant="danger" onPress={onLogout} loading={busy} />
      </View>
    </Screen>
  );
}
