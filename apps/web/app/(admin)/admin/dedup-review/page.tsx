import { Placeholder } from '@/components/admin/Placeholder';

export default function AdminDedupReviewPage() {
  return (
    <Placeholder
      title="Dedup review"
      sprint={5}
      taskId="T-212"
      description="kor-travel-map record linkage 후보를 검토하고 merge/split 결정을 추적."
      notes={[
        '중복 후보 목록, confidence, provider source 비교, 지도 preview.',
        'merge/split/reject 액션은 사유, diff, idempotency key를 요구.',
        'Pinvi는 검토 요청과 결과 조회만 담당하고 feature 저장소를 직접 수정하지 않음.',
      ]}
    />
  );
}
