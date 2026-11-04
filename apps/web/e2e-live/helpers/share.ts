/**
 * share(SHR) 영역 공용 유틸 — `../helpers/live` 계약 위에 얹는 얇은 래퍼.
 * UI 텍스트·testid 출처: F:\dev\pinvi\apps\web\components\trips\{TripDetail,TripShareLinks,
 * TripCompanions,TripComments,SharedTripView,TripActions}.tsx (README §selectors 참조).
 */
import { expect, test, type Page } from '@playwright/test';
import {
  apiBaseURL,
  createShareLink,
  e2ePrefix,
  isMobileProject,
  loginAs,
  openSharedInFreshContext,
  openTripTab,
  redact,
  requireEnv,
  sharedPath,
  user2Context,
  user2Email,
  type CreatedShareLink,
  type FreshSharedPage,
  type RecordedRequest,
  type ShareVisibility,
  type TripTab,
} from './live';

export {
  createShareLink,
  isMobileProject,
  loginAs,
  openSharedInFreshContext,
  openTripTab,
  redact,
  requireEnv,
  sharedPath,
  user2Context,
  user2Email,
  type CreatedShareLink,
  type FreshSharedPage,
  type RecordedRequest,
  type ShareVisibility,
  type TripTab,
};

export function uniqueTitle(tag: string): string {
  return `${e2ePrefix} SHR ${tag} ${Date.now()}`;
}

export const sharedApiRe = (tripId: string) => new RegExp(`/trips/${tripId}/shared/[^/?#]+`);

export async function gotoTrip(page: Page, tripId: string, title?: string): Promise<void> {
  await page.goto(`/trips/${tripId}`);
  await expect(page.getByTestId('trip-detail-shell')).toBeVisible();
  if (title) await expect(page.getByRole('heading', { name: title }).first()).toBeVisible();
}

export const shareSection = (page: Page) => page.getByRole('region', { name: '공유 링크' });
export const companionSection = (page: Page) => page.getByRole('region', { name: '동반자' });
export const commentSection = (page: Page) => page.getByRole('region', { name: '댓글' });

export async function expectSharedError(page: Page, messagePart: string | RegExp): Promise<void> {
  const error = page.getByTestId('shared-error');
  await expect(error).toBeVisible();
  await expect(error.getByRole('heading', { name: '공유 링크를 열 수 없어요' })).toBeVisible();
  await expect(error.getByRole('alert')).toContainText(messagePart);
  await expect(error.getByRole('link', { name: '홈으로' })).toBeVisible();
  await expect(error.getByRole('link', { name: '로그인' })).toBeVisible();
}

/** 읽기 전용 공유 뷰의 골격 + 편집 UI 부재를 단언한다. */
export async function expectSharedReadOnly(page: Page, title: string): Promise<void> {
  await expect(page.getByText('공유된 여행 · 읽기 전용')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  await expect(page.getByRole('region', { name: '여행 지도' })).toBeVisible();
  await expect(page.getByRole('complementary', { name: '장소 목록' })).toBeVisible();
  await expect(page.getByRole('button', { name: '마커 편집' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '장소 삭제' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '링크 만들기' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: '공유' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '댓글' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '로그인' }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: '시작하기' }).first()).toBeVisible();
}

/**
 * API base(origin + prefix) — 공용 `apiBaseURL` 위임. 페이지가 이미 API 요청을 했으면 즉시,
 * 아니면 /login 을 열어 탐지한다. `PINVI_E2E_API_URL` 이 있으면 그것을 우선한다.
 */
export function apiBaseFromPage(page: Page): () => Promise<string> {
  return () => apiBaseURL(page);
}

export type CompanionRole = 'editor' | 'viewer' | 'co_owner';

/** '동행' 탭이 열린 상태에서 초대한다. 이메일 값은 로그에 남기지 않는다. */
export async function inviteCompanion(page: Page, email: string, role: CompanionRole): Promise<void> {
  const section = companionSection(page);
  await section.getByLabel('이메일').fill(email);
  await section.getByLabel('권한').selectOption(role);
  // Report the server's answer instead of failing later on a missing list (status only, no body).
  const invited = page
    .waitForResponse((r) => r.request().method() === 'POST' && /\/trips\/[^/]+\/members$/.test(new URL(r.url()).pathname), {
      timeout: 30_000,
    })
    .catch(() => null);
  await section.getByRole('button', { name: '초대' }).click();
  const res = await invited;
  if (res) test.info().annotations.push({ type: 'invite', description: `POST members → ${res.status()}` });
}

export async function postComment(page: Page, body: string): Promise<void> {
  const section = commentSection(page);
  await section.getByLabel('댓글 입력').fill(body);
  await section.getByRole('button', { name: '작성' }).click();
  await expect(page.getByTestId('trip-comment-list')).toContainText(body);
}
