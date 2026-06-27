import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminSeedPage() {
  return (
    <Placeholder
      title="시드 시나리오 (dev only)"
      sprint={3}
      taskId="T-214"
      description="개발/스테이징 전용 시나리오 8개. 운영 환경에서는 라우트 자체 미등록."
      notes={[
        'POST /admin/seed/{scenario} — dev/staging only, 운영 API router 미등록.',
        '시나리오: empty, basic, trips, notice-plans, audit, emails, full, e2e.',
        '로컬 임시 bootstrap 계정은 추적 문서에 credential 조합을 남기지 않음.',
      ]}
    />
  );
}
