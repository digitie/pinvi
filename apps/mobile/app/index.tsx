import { View, Text } from 'react-native';
import { TripStatusSchema } from '@pinvi/schemas';
import { queryKeys } from '@pinvi/api-client';

// 공용 패키지 import 검증 — frontend.md §6.2 step 2.
// @pinvi/schemas(Zod)와 @pinvi/api-client(query key factory)를 웹과 동일하게 import.
const tripStatusCount = TripStatusSchema.options.length;
const queryNamespaces = Object.keys(queryKeys).length;

export default function HomeScreen() {
  return (
    <View className="flex-1 items-center justify-center gap-2 bg-canvas px-6">
      <Text className="text-xl font-semibold text-ink">Pinvi 모바일 (Expo)</Text>
      <Text className="text-center text-sm text-ink">
        @pinvi/* 공용 패키지 연결 확인 — trip status {tripStatusCount}종, query
        namespace {queryNamespaces}개.
      </Text>
      <Text className="text-center text-xs text-ink">
        구조 스캐폴드(ADR-041). 화면 구현은 Sprint M-1.
      </Text>
    </View>
  );
}
