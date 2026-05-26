import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminResetPage() {
  return (
    <Placeholder
      title="DB 리셋 (dev only)"
      sprint={3}
      description="개발/스테이징 전용. 운영 환경에서는 라우트 자체 미등록."
      notes={[
        'POST /admin/reset — confirm 다이얼로그 + 사유 입력',
        'DB 전체 truncate + alembic re-apply',
        '운영 환경(`APP_ENV=production`)에서는 404',
      ]}
    />
  );
}
