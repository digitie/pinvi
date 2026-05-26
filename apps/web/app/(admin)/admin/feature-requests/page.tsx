import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminFeatureRequestsPage() {
  return (
    <Placeholder
      title="Feature 요청 큐"
      sprint={6}
      description="사용자 feature 요청 큐 → 라이브러리 적재 trigger."
      notes={[
        'GET /admin/feature-requests (status 필터)',
        'POST /admin/feature-requests/{id}/approve — 승인 시 라이브러리 트리거',
        'POST /admin/feature-requests/{id}/reject',
      ]}
    />
  );
}
