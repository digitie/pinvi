import { useState } from 'react';
import { View } from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import type { TripVisibility } from '@pinvi/schemas';
import {
  VISIBILITY_LABEL,
  friendlyErrorText,
  validateTripDateRange,
  type TripDateRangeError,
} from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Body,
  Button,
  Card,
  ChipGroup,
  ErrorBanner,
  Field,
  Heading,
  Screen,
} from '../../../components/ui';

const VISIBILITY_OPTIONS = (Object.keys(VISIBILITY_LABEL) as TripVisibility[]).map((v) => ({
  value: v,
  label: VISIBILITY_LABEL[v],
}));

/** 새 여행 만들기 — 웹 `(app)/trips` 생성 흐름 대응. `tripApi.create`. */
export default function NewTripScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [regionHint, setRegionHint] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [visibility, setVisibility] = useState<TripVisibility>('private');
  const [error, setError] = useState<string | null>(null);
  // 날짜 검증(웹 TripDashboard.validateDateRange 대응) — 형식/함께 입력/순서. 필드에 붙여 표시.
  const [dateError, setDateError] = useState<TripDateRangeError | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      api.trips.create({
        title: title.trim(),
        region_hint: regionHint.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        visibility,
        companions: [],
      }),
    onSuccess: (trip) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.all() });
      router.replace(`/trips/${trip.trip_id}`);
    },
    onError: (err) => setError(friendlyErrorText(err)),
  });

  const onSubmit = () => {
    if (!title.trim()) {
      setError('제목을 입력해 주세요.');
      return;
    }
    const nextDateError = validateTripDateRange(startDate, endDate);
    setDateError(nextDateError);
    if (nextDateError) {
      setError(null);
      return;
    }
    setError(null);
    createMutation.mutate();
  };

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-1">
          <Heading>새 여행</Heading>
          <Body>여행 제목만 있으면 시작할 수 있어요. 나머지는 나중에 편집해도 됩니다.</Body>
        </View>

        <Card className="gap-3">
          <ErrorBanner message={error} />
          <Field
            label="제목"
            value={title}
            onChangeText={setTitle}
            maxLength={200}
            placeholder="예: 제주 가족 여행"
            returnKeyType="next"
          />
          <Field
            label="지역 (선택)"
            value={regionHint}
            onChangeText={setRegionHint}
            maxLength={120}
            placeholder="예: 제주"
          />
          <Field
            label="시작일 (YYYY-MM-DD, 선택)"
            value={startDate}
            onChangeText={(v) => {
              setStartDate(v);
              setDateError(null);
            }}
            error={dateError?.field === 'startDate' ? dateError.message : undefined}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
            placeholder="2026-07-01"
          />
          <Field
            label="종료일 (YYYY-MM-DD, 선택)"
            value={endDate}
            onChangeText={(v) => {
              setEndDate(v);
              setDateError(null);
            }}
            error={dateError?.field === 'endDate' ? dateError.message : undefined}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
            placeholder="2026-07-03"
          />
          <ChipGroup
            label="공개 범위"
            value={visibility}
            options={VISIBILITY_OPTIONS}
            onChange={setVisibility}
          />
          <Button label="만들기" onPress={onSubmit} loading={createMutation.isPending} />
        </Card>
      </View>
    </Screen>
  );
}
