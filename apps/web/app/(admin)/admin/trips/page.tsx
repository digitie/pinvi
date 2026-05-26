import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminTripsPage() {
  return (
    <Placeholder
      title="여행"
      sprint={3}
      description="여행 목록 / 상세 + 멤버 / POI / 공유 토큰. Sprint 4에 데이터 적재 후 결선."
      notes={[
        'GET /admin/trips, /admin/trips/{id}',
        '필터: status, visibility, owner',
        '상세: companion list, share token, POI 트리, copy_lineage',
      ]}
    />
  );
}
