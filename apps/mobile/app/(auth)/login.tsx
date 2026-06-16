import { useRef, useState } from 'react';
import { TextInput, View } from 'react-native';
import { Link } from 'expo-router';
import { LoginRequestSchema } from '@pinvi/schemas';
import { ApiError } from '@pinvi/api-client';
import { validateForm, type FieldErrors } from '@pinvi/domain';
import { useAuth } from '../../lib/auth';
import { Body, Button, ErrorBanner, Field, Heading, Screen } from '../../components/ui';

/**
 * 로그인 화면 — 웹 `apps/web/app/(auth)/login/page.tsx` 대응.
 * 공용 `LoginRequestSchema` + `validateForm`(한국어 오류) 재사용. 성공 시 인증 상태가
 * 바뀌면 `(auth)/_layout` 가드가 홈으로 리다이렉트한다. (OAuth/소셜은 후속.)
 */
export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const passwordRef = useRef<TextInput>(null);

  const onSubmit = async () => {
    setError(null);
    const result = validateForm(LoginRequestSchema, { email, password });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      return;
    }

    setLoading(true);
    try {
      await login(result.data);
      // 성공 시 상태 전환 → 그룹 가드가 홈으로 이동.
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'EMAIL_NOT_VERIFIED') {
          setError('이메일 인증이 필요합니다. 메일을 확인해 주세요.');
        } else if (err.code === 'AUTH_INVALID_CREDENTIALS') {
          setError('이메일 또는 비밀번호가 올바르지 않습니다.');
        } else {
          setError(err.message);
        }
      } else {
        setError('로그인 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <View className="flex-1 justify-center gap-6">
        <View className="gap-2">
          <Heading>로그인</Heading>
          <Body>Pinvi 계정으로 여행을 계획하고 기록하세요.</Body>
        </View>

        <View className="gap-4">
          <ErrorBanner message={error} />
          <Field
            label="이메일"
            value={email}
            onChangeText={setEmail}
            error={fieldErrors.email}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            inputMode="email"
            returnKeyType="next"
            onSubmitEditing={() => passwordRef.current?.focus()}
            placeholder="you@example.com"
          />
          <Field
            ref={passwordRef}
            label="비밀번호"
            value={password}
            onChangeText={setPassword}
            error={fieldErrors.password}
            secureTextEntry
            autoComplete="password"
            returnKeyType="go"
            onSubmitEditing={onSubmit}
            placeholder="비밀번호"
          />
          <Button label="로그인" onPress={onSubmit} loading={loading} />
        </View>

        <View className="flex-row items-center justify-center gap-1">
          <Body>아직 계정이 없으신가요?</Body>
          <Link href="/signup" className="text-sm font-semibold text-primary">
            회원가입
          </Link>
        </View>
      </View>
    </Screen>
  );
}
