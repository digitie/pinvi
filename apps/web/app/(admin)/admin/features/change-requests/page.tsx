import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminFeatureChangeRequestsPage() {
  return (
    <Placeholder
      title="Feature 변경 요청"
      sprint={4}
      taskId="T-210"
      description="사용자·운영자 변경 요청을 kor-travel-map admin change API로 전달하기 전 검토."
      notes={[
        'Feature 생성/수정/병합 요청 목록, 상태 필터, 대상 feature link.',
        '승인 전 diff preview, 사유 입력, idempotency key, 감사 로그 기록.',
        'kor-travel-map 장애 또는 kill-switch 활성 시 mutation 버튼 비활성.',
      ]}
    />
  );
}
