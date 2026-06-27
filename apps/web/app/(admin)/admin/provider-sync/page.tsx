import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminProviderSyncPage() {
  return (
    <Placeholder
      title="Provider sync"
      sprint={5}
      taskId="T-211"
      description="provider별 수집·정규화 실행 현황과 재시도 요청을 Dagster/kor-travel-map 계약으로 연결."
      notes={[
        'provider별 마지막 실행, 다음 실행, 처리/실패 건수, rate limit 상태.',
        '수동 재시도는 kill-switch, 사유 입력, 감사 로그, idempotency key를 통과해야 함.',
        '상세 로그는 /admin/debug/logs, 정합성 결과는 /admin/integrity와 연결.',
      ]}
    />
  );
}
