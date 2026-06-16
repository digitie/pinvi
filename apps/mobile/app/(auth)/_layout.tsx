import { Redirect, Stack } from 'expo-router';
import { useAuth } from '../../lib/auth';

/**
 * 비인증 그룹(로그인/회원가입/이메일 인증). 이미 인증된 사용자는 홈(`/`)으로 보낸다.
 * 웹 `apps/web/app/(auth)/*` route group 대응 — 단, 프로필/계정 화면은 모바일에서
 * 인증 그룹 `(app)/profile`로 둔다(클라이언트 가드 경계, expo-implementation-plan §7).
 */
export default function AuthLayout() {
  const { status } = useAuth();

  if (status === 'authenticated') {
    return <Redirect href="/" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
