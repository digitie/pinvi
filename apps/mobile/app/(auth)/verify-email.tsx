import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
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

export default function VerifyEmailScreen() {
  const { adoptSession } = useAuth();
  const params = useLocalSearchParams<{ token?: string; email?: string; dispatched?: string }>();
  const token = typeof params.token === 'string' ? params.token : undefined;
  const email = typeof params.email === 'string' ? params.email : undefined;
  const dispatched = params.dispatched !== 'false';

  const [state, setState] = useState<VerifyState>(token ? 'verifying' : 'pending');
  const [error, setError] = useState<string | null>(null);

  const verify = useCallback(
    async (rawToken: string) => {
      setState('verifying');
      setError(null);
      const parsed = VerifyEmailRequestSchema.safeParse({ token: rawToken });
      if (!parsed.success) {
        setState('error');
        setError('인증 링크가 올바르지 않습니다. 메일의 링크를 다시 확인해 주세요.');
        return;
      }
      try {
        const result = await api.mobileAuth.verifyEmail(parsed.data);
        await adoptSession(result);
        // 세션 확정 → `(auth)/_layout` 가드가 홈으로 이동.
      } catch (err) {
        setState('error');
        if (err instanceof ApiError && err.code === 'VERIFICATION_TOKEN_INVALID') {
          setError('인증 링크가 만료되었거나 이미 사용되었습니다. 다시 요청해 주세요.');
        } else {
          setError('이메일 인증에 실패했습니다. 잠시 후 다시 시도해 주세요.');
        }
      }
    },
    [adoptSession],
  );

  useEffect(() => {
    if (token) {
      void verify(token);
    }
  }, [token, verify]);

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
