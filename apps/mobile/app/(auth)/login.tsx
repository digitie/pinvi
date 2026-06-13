import { View, Text } from 'react-native';

// 웹 apps/web/app/(auth)/login/page.tsx 대응 placeholder.
// 폼은 @pinvi/schemas의 LoginRequestSchema + react-hook-form zodResolver로
// 웹과 동일 검증을 쓴다 (frontend.md §4.5) — 구현은 Sprint M-1.
export default function LoginScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-canvas px-6">
      <Text className="text-base text-ink">로그인 (placeholder)</Text>
    </View>
  );
}
