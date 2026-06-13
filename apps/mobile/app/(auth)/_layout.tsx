import { Stack } from 'expo-router';

// 웹 apps/web/app/(auth)/ route group 대응 (frontend.md §8 — 동일 라우트 트리).
export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
