import { useState } from 'react';
import { View } from 'react-native';
import { ApiError } from '@pinvi/api-client';
import { friendlyErrorText } from '@pinvi/domain';
import { useAuth } from '../../lib/auth';
import { api } from '../../lib/api';
import {
  Badge,
  Body,
  Button,
  Card,
  ErrorBanner,
  Heading,
  Muted,
  Screen,
  Subheading,
} from '../../components/ui';

const STATUS_LABELS: Record<string, string> = {
  pending_verification: '이메일 인증 대기',
  pending_profile: '프로필 작성 대기',
  active: '활성',
  disabled: '비활성',
};

/**
 * 프로필/계정 화면 — 웹 `(auth)/profile` 대응(모바일은 인증 그룹 `(app)`에 둔다).
 * 계정 정보 표시 + 로그아웃 + Google 연결 해제. OAuth 연결(시작)은 앱 딥링크 redirect가
 * 필요하므로 후속(expo-implementation-plan §5.4).
 */
export default function ProfileScreen() {
  const { user, logout, refreshUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) {
    return null;
  }

  const google = user.oauth_identities.find((i) => i.provider === 'google');

  const onUnlinkGoogle = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.auth.unlinkGoogleOAuth();
      await refreshUser();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'OAUTH_UNLINK_LAST_CREDENTIAL'
          ? '마지막 로그인 수단은 해제할 수 없습니다. 비밀번호를 먼저 설정해 주세요.'
          : friendlyErrorText(err),
      );
    } finally {
      setBusy(false);
    }
  };

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
        <Heading>프로필</Heading>
        <ErrorBanner message={error} />

        <Card className="gap-2">
          <Subheading>{user.nickname ?? '닉네임 미설정'}</Subheading>
          <Body>{user.email}</Body>
          <View className="flex-row flex-wrap gap-2 pt-1">
            <Badge label={STATUS_LABELS[user.status] ?? user.status} />
            {user.roles
              .filter((r) => r !== 'user')
              .map((r) => (
                <Badge key={r} label={r} />
              ))}
            {user.email_verified_at ? <Badge label="이메일 인증됨" /> : null}
          </View>
        </Card>

        <Card className="gap-3">
          <Subheading>소셜 연결</Subheading>
          {google ? (
            <View className="gap-2">
              <Body>
                Google · {google.provider_email ?? google.display_name ?? '연결됨'}
              </Body>
              <Button
                label="Google 연결 해제"
                variant="secondary"
                onPress={onUnlinkGoogle}
                loading={busy}
              />
            </View>
          ) : (
            <Muted>연결된 소셜 계정이 없습니다. (앱 내 연결은 추후 지원)</Muted>
          )}
        </Card>

        <Button label="로그아웃" variant="danger" onPress={onLogout} loading={busy} />
      </View>
    </Screen>
  );
}
