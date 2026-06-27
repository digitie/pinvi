import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminDebugLogsPage() {
  return (
    <Placeholder
      title="Debug logs"
      sprint={5}
      taskId="T-212"
      description="운영자가 provider/API 오류를 추적하되 PII·secret·실도메인을 노출하지 않는 로그 뷰."
      notes={[
        'provider, endpoint group, request_id, status, error class, latency 필터.',
        '본문 원문과 secret 값은 노출하지 않고 mask/sanitize 결과만 표시.',
        'API 호출 로그, provider sync, integrity 실패 화면에서 deep link.',
      ]}
    />
  );
}
