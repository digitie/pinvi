import { useRef, useState } from 'react';
import { TextInput, View } from 'react-native';
import { Link, useRouter } from 'expo-router';
import { RegisterRequestSchema } from '@pinvi/schemas';
import type { ConsentType } from '@pinvi/schemas';
import { ApiError } from '@pinvi/api-client';
import { validateForm, type FieldErrors } from '@pinvi/domain';
import { api } from '../../lib/api';
import {
  Body,
  Button,
  Card,
  Checkbox,
  ErrorBanner,
  Field,
  Heading,
  Muted,
  Screen,
  Subheading,
} from '../../components/ui';

/**
 * 회원가입 화면 — 웹 `apps/web/app/(auth)/signup/page.tsx` 대응.
 * 필수 약관 4종 + 선택 1종, 공용 `RegisterRequestSchema` + `validateForm` 재사용.
 * 가입 성공 시 이메일 인증 대기 안내(`verify-email`)로 이동한다.
 */
const CONSENT_VERSION = 'v1.0';

const REQUIRED_CONSENTS: { type: ConsentType; label: string; summary: string }[] = [
  { type: 'tos', label: '이용약관', summary: '서비스 이용 조건과 계정 운영 기준' },
  { type: 'privacy', label: '개인정보 처리방침', summary: '계정·여행계획·첨부파일 처리 기준' },
  { type: 'lbs_tos', label: '위치기반서비스 이용약관', summary: '여행 지도와 위치 기능 이용 조건' },
  {
    type: 'location_collection',
    label: '개인위치정보 수집·이용',
    summary: '현재 위치 기반 검색과 일정 표시',
  },
];
const OPTIONAL_CONSENTS: { type: ConsentType; label: string; summary: string }[] = [
  { type: 'marketing', label: '마케팅·이벤트 이메일 수신', summary: '업데이트·이벤트·베타 안내' },
];

type ConsentState = Partial<Record<ConsentType, boolean>>;

export default function SignupScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [consents, setConsents] = useState<ConsentState>({});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const passwordRef = useRef<TextInput>(null);
  const nicknameRef = useRef<TextInput>(null);

  const allRequired = REQUIRED_CONSENTS.every((item) => consents[item.type]);

  const toggle = (type: ConsentType, next: boolean) =>
    setConsents((current) => ({ ...current, [type]: next }));

  const onSubmit = async () => {
    setError(null);
    if (!allRequired) {
      setError('필수 약관에 모두 동의해 주세요.');
      return;
    }

    const consentItems = [...REQUIRED_CONSENTS, ...OPTIONAL_CONSENTS]
      .filter((item) => consents[item.type])
      .map((item) => ({ consent_type: item.type, version: CONSENT_VERSION }));

    const result = validateForm(RegisterRequestSchema, {
      email,
      password,
      nickname,
      consents: consentItems,
    });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      return;
    }

    setLoading(true);
    try {
      const registered = await api.auth.register(result.data);
      router.replace(
        `/verify-email?email=${encodeURIComponent(result.data.email)}&dispatched=${registered.verification_email_dispatched}`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.code === 'EMAIL_ALREADY_USED' ? '이미 가입된 이메일입니다.' : err.message);
      } else {
        setError('알 수 없는 오류가 발생했습니다.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Screen>
      <View className="gap-6 py-6">
        <Heading>회원가입</Heading>

        <View className="gap-4">
          <ErrorBanner message={error} />
          <Field
            label="이메일"
            value={email}
            onChangeText={setEmail}
            error={fieldErrors.email}
            autoCapitalize="none"
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
            returnKeyType="next"
            onSubmitEditing={() => nicknameRef.current?.focus()}
            placeholder="8자 이상"
          />
          <Field
            ref={nicknameRef}
            label="닉네임"
            value={nickname}
            onChangeText={setNickname}
            error={fieldErrors.nickname}
            returnKeyType="done"
            placeholder="여행자 닉네임"
          />
        </View>

        <Card className="gap-1">
          <Subheading>필수 약관 동의</Subheading>
          {fieldErrors.consents ? <Muted className="text-error-text">{fieldErrors.consents}</Muted> : null}
          {REQUIRED_CONSENTS.map((item) => (
            <Checkbox
              key={item.type}
              checked={Boolean(consents[item.type])}
              onToggle={(next) => toggle(item.type, next)}
              label={item.label}
              summary={item.summary}
            />
          ))}
        </Card>

        <Card className="gap-1">
          <Subheading>선택 동의</Subheading>
          {OPTIONAL_CONSENTS.map((item) => (
            <Checkbox
              key={item.type}
              checked={Boolean(consents[item.type])}
              onToggle={(next) => toggle(item.type, next)}
              label={item.label}
              summary={item.summary}
            />
          ))}
        </Card>

        <Button label="회원가입" onPress={onSubmit} loading={loading} disabled={!allRequired} />

        <View className="flex-row items-center justify-center gap-1">
          <Body>이미 계정이 있으신가요?</Body>
          <Link href="/login" className="text-sm font-semibold text-primary">
            로그인
          </Link>
        </View>
      </View>
    </Screen>
  );
}
