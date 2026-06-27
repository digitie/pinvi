import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminCategoryMappingPage() {
  return (
    <Placeholder
      title="카테고리 매핑"
      sprint={6}
      taskId="T-213"
      description="maki icon + 16색 P-01~P-16 마커 팔레트 매핑."
      notes={[
        'GET /admin/category-mappings, provider/category/source별 현재 매핑 조회.',
        'PUT /admin/category-mappings는 사유, diff preview, 감사 로그를 요구.',
        '16색 팔레트: P-01 ~ P-16, Pinvi wrapper에서만 관리.',
      ]}
    />
  );
}
