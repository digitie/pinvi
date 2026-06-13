'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import type { AdminUserDetail } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { FormTextArea } from '@/components/forms/FormTextArea';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

type ActionKind = 'force-verify' | 'disable' | 'reveal-email';

export default function AdminUserDetailPage() {
  const router = useRouter();
  const params = useParams<{ user_id: string }>();
  const userId = params.user_id;
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionKind | null>(null);
  const [reason, setReason] = useState('');
  const [acting, setActing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getUser(userId)
      .then((u) => !cancelled && setUser(u))
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/users');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [userId, router]);

  const onAction = async () => {
    if (!actionDialog || reason.trim().length < 1) return;
    setActing(true);
    try {
      const api = adminApi(apiClient);
      const accessReason = reason.trim();
      const updated =
        actionDialog === 'reveal-email'
          ? await api.revealUserPii(userId, { access_reason: accessReason })
          : actionDialog === 'force-verify'
            ? await api.forceVerify(userId, { access_reason: accessReason })
            : await api.disableUser(userId, { access_reason: accessReason });
      setUser(updated);
      setActionDialog(null);
      setReason('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '액션 실패');
    } finally {
      setActing(false);
    }
  };

  if (error) {
    return (
      <AdminPage title="사용자 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!user) {
    return (
      <AdminPage title="사용자 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  return (
    <AdminPage
      title={user.email_revealed ? user.email : user.email_masked}
      description={`user_id ${user.user_id}`}
      actions={
        <Link href="/admin/users" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-user-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-ink" data-testid="admin-user-email">
                {user.email}
              </span>
              {user.email_revealed ? (
                <span className="rounded-sm bg-surface-soft px-2 py-1 text-xs text-muted">
                  원본
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setActionDialog('reveal-email')}
                  className="rounded-sm border border-hairline px-2 py-1 text-xs"
                  data-testid="admin-user-reveal-email"
                >
                  원본 보기
                </button>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일 상태</dt>
            <dd>{user.email_status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">상태</dt>
            <dd>{user.status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">역할</dt>
            <dd>{user.roles.join(', ')}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">활성 여부</dt>
            <dd>{user.is_active ? 'Y' : 'N'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일 인증</dt>
            <dd>{user.email_verified_at ?? '미인증'}</dd>
          </div>
        </dl>
      </Section>

      <Section title="액션 (admin role만)">
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            disabled={!!user.email_verified_at}
            onClick={() => setActionDialog('force-verify')}
            className="rounded-sm border border-primary px-3 py-2 text-sm text-primary disabled:opacity-50"
            data-testid="admin-user-force-verify"
          >
            force-verify
          </button>
          <button
            type="button"
            disabled={user.status === 'disabled'}
            onClick={() => setActionDialog('disable')}
            className="rounded-sm border border-error-text px-3 py-2 text-sm text-error-text disabled:opacity-50"
            data-testid="admin-user-disable"
          >
            disable
          </button>
        </div>
      </Section>

      <Section title="최근 Audit">
        <div className="overflow-x-auto" data-testid="admin-user-audit-list">
          <table className="min-w-full divide-y divide-hairline text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-2">액션</th>
                <th className="px-2 py-2">사유</th>
                <th className="px-2 py-2">PII</th>
                <th className="px-2 py-2">시각</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {user.recent_audit.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-2 py-4 text-center text-muted">
                    기록이 없습니다.
                  </td>
                </tr>
              ) : (
                user.recent_audit.map((row) => (
                  <tr key={row.log_id}>
                    <td className="whitespace-nowrap px-2 py-2 font-mono text-xs">
                      {row.action}
                    </td>
                    <td className="px-2 py-2">{row.access_reason ?? '—'}</td>
                    <td className="whitespace-nowrap px-2 py-2">
                      {row.target_pii_fields?.join(', ') ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-muted">
                      {new Date(row.occurred_at).toLocaleString('ko-KR')}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      {actionDialog && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-4 rounded-sm bg-white p-6">
            <h3 className="text-lg font-bold text-ink">
              {actionDialog === 'reveal-email'
                ? '이메일 원본 보기'
                : actionDialog === 'force-verify'
                  ? '강제 이메일 인증'
                  : '사용자 비활성화'}
            </h3>
            <FormTextArea
              id="admin-user-action-reason"
              label="사유"
              hint="사유는 감사 로그에 기록됩니다. (최소 1자, 최대 500자)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              data-testid="admin-user-action-reason"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setActionDialog(null);
                  setReason('');
                }}
                className="rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                취소
              </button>
              <button
                type="button"
                disabled={acting || reason.trim().length < 1}
                onClick={onAction}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-user-action-confirm"
              >
                {acting ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminPage>
  );
}
