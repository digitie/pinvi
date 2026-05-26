import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminCategoryMappingPage() {
  return (
    <Placeholder
      title="카테고리 매핑"
      sprint={6}
      description="maki icon + 16색 P-01~P-16 마커 팔레트 매핑. category_mappings 테이블."
      notes={[
        'GET /admin/category-mappings',
        'PUT /admin/category-mappings — 자유 편집',
        '16색 팔레트: P-01 ~ P-16 (DESIGN.md 참고)',
      ]}
    />
  );
}
