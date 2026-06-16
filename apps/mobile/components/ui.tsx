import { forwardRef, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

/**
 * 모바일 RN UI 키트(NativeWind). 웹 shadcn/ui 대응 — 각자 구현(frontend.md §2.1).
 * 색/타이포는 @pinvi/design-tokens preset(`tailwind.config.js`)에서 온다.
 */

/** 화면 컨테이너 — SafeArea + 스크롤 + canvas 배경. */
export function Screen({
  children,
  scroll = true,
  contentClassName,
}: {
  children: ReactNode;
  scroll?: boolean;
  contentClassName?: string;
}) {
  const inner = (
    <View className={`flex-1 px-5 py-4 ${contentClassName ?? ''}`}>{children}</View>
  );
  return (
    <SafeAreaView className="flex-1 bg-canvas" edges={['top', 'bottom']}>
      {scroll ? (
        <ScrollView
          className="flex-1"
          contentContainerClassName="flex-grow"
          keyboardShouldPersistTaps="handled"
        >
          {inner}
        </ScrollView>
      ) : (
        inner
      )}
    </SafeAreaView>
  );
}

export function Heading({ children, className }: { children: ReactNode; className?: string }) {
  return <Text className={`text-2xl font-bold text-ink ${className ?? ''}`}>{children}</Text>;
}

export function Subheading({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <Text className={`text-base font-semibold text-ink ${className ?? ''}`}>{children}</Text>
  );
}

export function Body({ children, className }: { children: ReactNode; className?: string }) {
  return <Text className={`text-sm text-body ${className ?? ''}`}>{children}</Text>;
}

export function Muted({ children, className }: { children: ReactNode; className?: string }) {
  return <Text className={`text-xs text-muted ${className ?? ''}`}>{children}</Text>;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <View
      className={`rounded-md border border-hairline-soft bg-canvas p-4 ${className ?? ''}`}
    >
      {children}
    </View>
  );
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

const BUTTON_BG: Record<ButtonVariant, string> = {
  primary: 'bg-primary',
  secondary: 'bg-surface-strong',
  ghost: 'bg-transparent',
  danger: 'bg-error-bg',
};
const BUTTON_TEXT: Record<ButtonVariant, string> = {
  primary: 'text-white',
  secondary: 'text-ink',
  ghost: 'text-primary',
  danger: 'text-error-text',
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  className,
}: {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}) {
  const isOff = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: isOff, busy: loading }}
      disabled={isOff}
      onPress={onPress}
      className={`min-h-12 flex-row items-center justify-center rounded-md px-4 py-3 ${BUTTON_BG[variant]} ${isOff ? 'opacity-50' : 'active:opacity-80'} ${className ?? ''}`}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? '#ffffff' : '#222222'} />
      ) : (
        <Text className={`text-base font-semibold ${BUTTON_TEXT[variant]}`}>{label}</Text>
      )}
    </Pressable>
  );
}

/** 라벨 + TextInput + 오류 메시지(공용 validateForm 결과 결선용). */
export const Field = forwardRef<TextInput, TextInputProps & { label: string; error?: string }>(
  function Field({ label, error, className, ...props }, ref) {
    return (
      <View className="gap-1.5">
        <Text className="text-sm font-medium text-ink">{label}</Text>
        <TextInput
          ref={ref}
          placeholderTextColor="#929292"
          className={`min-h-12 rounded-md border bg-canvas px-3 py-3 text-base text-ink ${error ? 'border-error-text' : 'border-hairline'} ${className ?? ''}`}
          {...props}
        />
        {error ? (
          <Text className="text-xs text-error-text" accessibilityLiveRegion="polite">
            {error}
          </Text>
        ) : null}
      </View>
    );
  },
);

/** 폼 상단 일반 오류 배너. */
export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <View className="rounded-md bg-error-bg px-3 py-2.5">
      <Text className="text-sm text-error-text">{message}</Text>
    </View>
  );
}

/** 목록 빈 상태. */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <View className="items-center gap-2 py-16">
      <Text className="text-base font-semibold text-ink">{title}</Text>
      {description ? <Text className="text-center text-sm text-muted">{description}</Text> : null}
      {action ? <View className="mt-2">{action}</View> : null}
    </View>
  );
}

/** 쿼리 오류 + 재시도. */
export function ErrorView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View className="items-center gap-3 py-16">
      <Text className="text-center text-sm text-error-text">{message}</Text>
      {onRetry ? <Button label="다시 시도" variant="secondary" onPress={onRetry} /> : null}
    </View>
  );
}

/** 중앙 로딩 스피너. */
export function Loading() {
  return (
    <View className="flex-1 items-center justify-center py-16">
      <ActivityIndicator color="#ff385c" />
    </View>
  );
}

/** 체크박스 + 라벨/요약(동의 항목 등). */
export function Checkbox({
  checked,
  onToggle,
  label,
  summary,
}: {
  checked: boolean;
  onToggle: (next: boolean) => void;
  label: string;
  summary?: string;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onToggle(!checked)}
      className="flex-row items-start gap-3 py-1.5"
    >
      <View
        className={`mt-0.5 h-5 w-5 items-center justify-center rounded-sm border ${checked ? 'border-primary bg-primary' : 'border-border-strong bg-canvas'}`}
      >
        {checked ? <Text className="text-xs font-bold text-white">✓</Text> : null}
      </View>
      <View className="flex-1">
        <Text className="text-sm font-medium text-ink">{label}</Text>
        {summary ? <Text className="text-xs text-muted">{summary}</Text> : null}
      </View>
    </Pressable>
  );
}

/** 단일 선택 칩 그룹(visibility/status 등 enum 선택). */
export function ChipGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <View className="gap-1.5">
      {label ? <Text className="text-sm font-medium text-ink">{label}</Text> : null}
      <View className="flex-row flex-wrap gap-2">
        {options.map((opt) => {
          const active = value === opt.value;
          return (
            <Pressable
              key={opt.value}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              onPress={() => onChange(opt.value)}
              className={`rounded-sm border px-3 py-2 ${active ? 'border-primary bg-primary' : 'border-hairline bg-canvas'}`}
            >
              <Text className={`text-sm font-medium ${active ? 'text-white' : 'text-body'}`}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** 색 점 + 라벨(상태/카테고리 뱃지). */
export function Badge({ label, className }: { label: string; className?: string }) {
  return (
    <View className={`self-start rounded-sm bg-surface-strong px-2 py-0.5 ${className ?? ''}`}>
      <Text className="text-xs font-medium text-body">{label}</Text>
    </View>
  );
}
