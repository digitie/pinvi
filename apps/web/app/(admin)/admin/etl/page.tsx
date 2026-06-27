import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminEtlPage() {
  return (
    <Placeholder
      title="ETL"
      sprint={5}
      taskId="T-211"
      description="Dagster asset/job 상태와 provider sync 실행 이력을 Admin에서 조회."
      notes={[
        'Dagster iframe은 Grafana와 분리해 유지하고, 이 페이지는 자체 요약 카드 중심.',
        '자산 카드: 상태, 마지막 실행, 다음 실행, 처리 건수, 실패 원인.',
        'provider별 sync 실행/재시도/kill-switch 상태는 /admin/provider-sync와 연결.',
      ]}
    />
  );
}
