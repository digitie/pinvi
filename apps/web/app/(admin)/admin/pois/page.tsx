import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminPoisPage() {
  return (
    <Placeholder
      title="POI"
      sprint={3}
      description="POI 검색 + feature_link_broken_at 필터. Sprint 4에 데이터 적재 후 결선."
      notes={[
        'GET /admin/pois (q, has_broken_link, trip_id)',
        '컬럼: poi_id, trip_day, feature_id, label, sort_order, broken_at',
        '액션: re-link to feature / unlink',
      ]}
    />
  );
}
