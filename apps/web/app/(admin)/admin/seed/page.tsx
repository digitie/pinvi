import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminSeedPage() {
  return (
    <Placeholder
      title="시드 시나리오 (dev only)"
      sprint={3}
      description="개발/스테이징 전용 시나리오 8개. 운영 환경에서는 라우트 자체 미등록."
      notes={[
        'POST /admin/seed/{scenario} — dev/staging only (운영 차단)',
        '시나리오: empty, basic, trips, notice-plans, audit, emails, full, e2e',
        'BOOTSTRAP_ADMIN_EMAIL 환경변수 필요',
      ]}
    />
  );
}
