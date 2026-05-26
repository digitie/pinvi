import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminApiCallsPage() {
  return (
    <Placeholder
      title="외부 API 호출 로그"
      sprint={3}
      description="api_call_log — provider/status/latency 필터. Sprint 4에 데이터 적재 후 결선."
      notes={[
        'GET /admin/api-calls (provider, status_code, latency 필터)',
        '컬럼: provider, endpoint, status, latency_ms, called_at',
        'detail 모달: req/resp 헤더 + body (PII 마스킹)',
      ]}
    />
  );
}
