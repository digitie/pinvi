import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminFeaturesPage() {
  return (
    <Placeholder
      title="Features"
      sprint={4}
      taskId="T-209"
      description="kor-travel-map OpenAPI 기반 feature 검색·상세·원천 조회."
      notes={[
        'GET /admin/features 검색, kind/status/provider 필터, bbox/행정구역 필터.',
        'GET /admin/features/{feature_id} 상세, sources, overrides, weather/price 보조 탭.',
        'Pinvi app DB에 직접 feature INSERT 금지, kor-travel-map HTTP 계약만 사용.',
      ]}
    />
  );
}
