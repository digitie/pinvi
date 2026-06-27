import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminResetPage() {
  return (
    <Placeholder
      title="DB 리셋 (dev only)"
      sprint={3}
      taskId="T-214"
      description="개발/스테이징 전용. 운영 환경에서는 라우트 자체 미등록."
      notes={[
        'POST /admin/reset — confirm 다이얼로그, 사유 입력, 재확인 토큰 요구.',
        'DB 전체 truncate + alembic re-apply는 dev/staging 전용.',
        '운영 환경에서는 router 미등록, API 응답은 404만 허용.',
      ]}
    />
  );
}
