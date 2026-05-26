import { AdminPage, Section } from '@/components/admin/AdminPage';

/**
 * `/admin` 대시보드.
 *
 * Sprint 3에서는 카드 8개 placeholder만. `/admin/stats/overview` endpoint는 Sprint 4에 결선.
 */
export default function AdminDashboardPage() {
  const cards: { label: string; value: string; hint: string }[] = [
    { label: '사용자 총 수', value: '—', hint: 'Sprint 4 결선' },
    { label: '24h 가입', value: '—', hint: '' },
    { label: '인증 대기', value: '—', hint: 'pending_verification' },
    { label: '여행 총 수', value: '—', hint: '' },
    { label: '활성 여행', value: '—', hint: 'status=active' },
    { label: 'POI 총 수', value: '—', hint: '' },
    { label: '이메일 큐 대기', value: '—', hint: 'email_queue.status=pending' },
    { label: 'ETL 24h', value: '—', hint: 'success / failed' },
  ];

  return (
    <AdminPage title="대시보드" description="운영 지표 8개 카드 — Sprint 4 결선 예정.">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid={`admin-stat-${card.label}`}
          >
            <p className="text-xs uppercase tracking-wide text-muted">{card.label}</p>
            <p className="mt-2 text-2xl font-bold text-ink">{card.value}</p>
            {card.hint && <p className="mt-1 text-xs text-muted">{card.hint}</p>}
          </div>
        ))}
      </div>

      <Section title="Sprint 3 범위">
        <ul className="list-inside list-disc space-y-1 text-sm text-ink">
          <li>RBAC + audit chain ✅</li>
          <li>사용자 목록/상세, force-verify, disable ✅</li>
          <li>이메일 큐 조회/재발송 ✅</li>
          <li>감사 로그 read-only + chain 검증 ✅</li>
          <li>여행/Feature/POI/API 호출 — placeholder (Sprint 4 결선)</li>
        </ul>
      </Section>
    </AdminPage>
  );
}
