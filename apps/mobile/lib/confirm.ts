import { Alert } from 'react-native';

/**
 * 파괴적 액션 확인 — 웹 `ConfirmDialog(tone='danger')` 대응(issue #215/#203).
 * 취소가 기본이고, 확인 버튼만 `destructive` 스타일로 mutate를 실행한다.
 */
export function confirmDestructive(options: {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
}): void {
  Alert.alert(options.title, options.message, [
    { text: '취소', style: 'cancel' },
    { text: options.confirmLabel, style: 'destructive', onPress: options.onConfirm },
  ]);
}
