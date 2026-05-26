import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminEtlPage() {
  return (
    <Placeholder
      title="ETL"
      sprint={5}
      description="Dagit reverse-proxy 임베드 + 자체 요약 페이지."
      notes={[
        'Dagit iframe + 자체 요약 카드',
        '자산 카드: 상태 / 마지막 실행 / 다음 실행 / 처리 건수',
        '자산 상세: 30일 이력 / 의존 그래프 / 에러 로그 / 입력 샘플',
      ]}
    />
  );
}
