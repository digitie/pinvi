'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, MessageSquare, Send, Trash2 } from 'lucide-react';
import { ApiError, authApi, tripApi } from '@pinvi/api-client';
import type { TripCommentResponse } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { canDeleteComment } from '@/lib/comments';

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(value)
  );
}

export interface TripCommentsProps {
  tripId: string;
}

export function TripComments({ tripId }: TripCommentsProps) {
  const [comments, setComments] = useState<TripCommentResponse[]>([]);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setComments(await tripApi(apiClient).listComments(tripId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '댓글을 불러오지 못했습니다.');
    }
  }, [tripId]);

  useEffect(() => {
    let cancelled = false;
    authApi(apiClient)
      .me()
      .then((me) => {
        if (!cancelled) setCurrentUserId(me.user_id);
      })
      .catch(() => {
        /* 비로그인/실패는 삭제 버튼만 숨김. */
      });
    void reload().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const post = async () => {
    const trimmed = body.trim();
    if (!trimmed) return;
    setPosting(true);
    setError(null);
    try {
      await tripApi(apiClient).createComment(tripId, { body: trimmed, target_type: 'trip' });
      setBody('');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '댓글 작성에 실패했습니다.');
    } finally {
      setPosting(false);
    }
  };

  const remove = async (commentId: string) => {
    setBusyId(commentId);
    setError(null);
    try {
      await tripApi(apiClient).deleteComment(tripId, commentId);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4" aria-label="댓글">
      <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
        <MessageSquare className="h-4 w-4 text-primary" aria-hidden="true" />
        댓글
      </h2>

      <div className="flex items-end gap-2">
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={2000}
          rows={2}
          placeholder="여행에 대한 의견을 남겨보세요."
          aria-label="댓글 입력"
          className="min-w-0 flex-1 rounded-sm border border-hairline px-2 py-1 text-sm text-ink outline-none focus:border-primary"
        />
        <button
          type="button"
          onClick={() => void post()}
          disabled={posting || !body.trim()}
          className="inline-flex h-9 shrink-0 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          {posting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="h-4 w-4" aria-hidden="true" />
          )}
          작성
        </button>
      </div>

      {error && <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>}

      {loading ? (
        <div className="flex h-16 items-center justify-center text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중…
        </div>
      ) : comments.length === 0 ? (
        <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
          아직 댓글이 없습니다.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="trip-comment-list">
          {comments.map((comment) => (
            <li key={comment.comment_id} className="rounded-sm border border-hairline px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 whitespace-pre-wrap break-words text-sm text-ink">
                  {comment.body}
                </p>
                {canDeleteComment(comment, currentUserId) && (
                  <button
                    type="button"
                    onClick={() => void remove(comment.comment_id)}
                    disabled={busyId === comment.comment_id}
                    aria-label="댓글 삭제"
                    className="shrink-0 rounded-sm p-1 text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
              <p className="mt-1 text-xs text-muted">{formatDateTime(comment.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
