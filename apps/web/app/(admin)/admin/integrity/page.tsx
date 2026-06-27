import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminIntegrityPage() {
  return (
    <Placeholder
      title="정합성"
      sprint={5}
      taskId="T-212"
      description="feature coverage, source freshness, linkage drift, OpenAPI drift를 운영 지표로 확인."
      notes={[
        '지역/feature kind별 coverage와 stale source count.',
        'OpenAPI schema drift, provider_sync 실패, linkage queue pending 요약.',
        '실패 항목은 담당 Task와 연결하고 N150 배치 검증 대상으로 승격.',
      ]}
    />
  );
}
