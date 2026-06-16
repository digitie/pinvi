import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../../../lib/auth';
import { mobileConfig } from '../../../lib/config';
import { Body, Button, Card, Heading, Muted, Screen, Subheading } from '../../../components/ui';

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

        <Pressable
          accessibilityRole="button"
          onPress={() => router.push('/profile')}
          className="rounded-md border border-hairline-soft bg-canvas p-4 active:opacity-80"
        >
          <Subheading>계정</Subheading>
          <Muted>{user?.email ?? '프로필·소셜 연결'}</Muted>
        </Pressable>

        <Card className="gap-3">
          <Subheading>준비 중</Subheading>
          <Body>텔레그램 알림 연동</Body>
          <Body>동의 항목 관리</Body>
          <Body>MCP 토큰</Body>
          <Muted>해당 설정 화면은 후속 스프린트에서 제공됩니다.</Muted>
        </Card>

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
