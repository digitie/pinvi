import { useEffect } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { VerifyEmailRequestSchema } from '@pinvi/schemas';
import { ApiError } from '@pinvi/api-client';
import { useAuth } from '../../lib/auth';
import { api } from '../../lib/api';
import { Body, Button, ErrorBanner, Heading, Loading, Muted, Screen } from '../../components/ui';

/**
 * 이메일 인증 화면 — 웹 `(auth)/verify-email` 대응.
 * 두 진입:
 *  1) 회원가입 직후 안내(`?email=&dispatched=`): "메일 확인" 대기 화면.
 *  2) 메일의 딥링크(`pinvi://verify-email?token=...`): 토큰 검증 → 세션 확정 → 가드가 홈 이동.
 */
type VerifyState = 'pending' | 'verifying' | 'error';

function verifyErrorText(err: unknown): string {
  if (err instanceof ApiError && err.code === 'VERIFICATION_TOKEN_INVALID') {
    return '인증 링크가 만료되었거나 이미 사용되었습니다. 다시 요청해 주세요.';
  }
  return '이메일 인증에 실패했습니다. 잠시 후 다시 시도해 주세요.';
}

export default function VerifyEmailScreen() {
  const { adoptSession } = useAuth();
  const params = useLocalSearchParams<{ token?: string; email?: string; dispatched?: string }>();
  const token = typeof params.token === 'string' ? params.token : undefined;
  const email = typeof params.email === 'string' ? params.email : undefined;
  const dispatched = params.dispatched !== 'false';

  // 검증은 mutation으로 — 상태(verifying/error)는 mutation에서 파생해 effect 안 setState를 없앤다.
  const verifyMutation = useMutation({
    mutationFn: async (rawToken: string) => {
      const parsed = VerifyEmailRequestSchema.safeParse({ token: rawToken });
      if (!parsed.success) {
        throw new Error('인증 링크가 올바르지 않습니다. 메일의 링크를 다시 확인해 주세요.');
      }
      const result = await api.mobileAuth.verifyEmail(parsed.data);
      await adoptSession(result);
      // 세션 확정 → `(auth)/_layout` 가드가 홈으로 이동.
    },
    retry: false,
  });
  const { mutate: verify } = verifyMutation;

  useEffect(() => {
    if (token) verify(token);
  }, [token, verify]);

  const state: VerifyState = verifyMutation.isError
    ? 'error'
    : token && (verifyMutation.isPending || verifyMutation.isIdle)
      ? 'verifying'
      : 'pending';
  const error = verifyMutation.isError
    ? verifyMutation.error instanceof ApiError
      ? verifyErrorText(verifyMutation.error)
      : verifyMutation.error.message
    : null;

  if (state === 'verifying') {
    return (
      <Screen scroll={false}>
        <View className="flex-1 items-center justify-center gap-4">
          <Loading />
          <Body>이메일을 인증하는 중입니다…</Body>
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <View className="flex-1 justify-center gap-6">
        <View className="gap-2">
          <Heading>이메일 인증</Heading>
          {state === 'error' ? (
            <ErrorBanner message={error} />
          ) : (
            <Body>
              {email ? `${email} 으로 ` : ''}
              {dispatched
                ? '인증 메일을 보냈습니다. 메일의 링크를 열어 인증을 완료해 주세요.'
                : '계정이 생성되었습니다. 인증 메일을 확인해 주세요(메일이 오지 않으면 잠시 후 다시 시도).'}
            </Body>
          )}
          <Muted>메일 링크를 열면 앱이 자동으로 인증을 처리합니다.</Muted>
        </View>

        {state === 'error' && token ? (
          <Button label="다시 시도" onPress={() => verify(token)} />
        ) : null}
      </View>
    </Screen>
  );
}
