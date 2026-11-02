/**
 * SHR 댓글 — 작성/삭제, 입력 검증, 두 신원 간 전파(탭 재진입), 작성자별 삭제 버튼.
 * 두 번째 신원은 일반 사용자 test2(PINVI_E2E_USER2_*). 댓글 수정 UI/API는 없다(SHR-021 blocked).
 * 일자/장소 대상 댓글 UI도 없다(SHR-022 blocked).
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, shot } from '../../helpers/live';
import {
  commentSection,
  companionSection,
  gotoTrip,
  inviteCompanion,
  isMobileProject,
  openTripTab,
  postComment,
  uniqueTitle,
  user2Context,
  user2Email,
} from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 댓글', () => {
  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-019 댓글 작성 → 목록 표시 → 삭제 (desktop+mobile)', async ({ page }) => {
    const title = uniqueTitle('019');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '댓글');

    const section = commentSection(page);
    await expect(section).toContainText('아직 댓글이 없습니다.');
    const body = `[e2e] SHR-019 댓글 ${Date.now()}`;
    await postComment(page, body);
    const list = page.getByTestId('trip-comment-list');
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(section.getByLabel('댓글 입력')).toHaveValue('');
    await expect(list.getByRole('listitem').first()).toContainText(/\d{2}\. \d{1,2}\. \d{1,2}\./);
    await shot(page, 'SHR-019', '01-comment-posted');

    await list.getByRole('button', { name: '댓글 삭제' }).click();
    await expect(section).toContainText('아직 댓글이 없습니다.');
    await expect(page.getByTestId('trip-comment-list')).toHaveCount(0);
  });

  test('SHR-020 댓글 입력 검증 — 공백만이면 비활성, 최대 2000자', async ({ page }) => {
    test.skip(({ isMobile }) => isMobile, '데스크톱 전용(긴 입력)');
    const title = uniqueTitle('020');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '댓글');

    const section = commentSection(page);
    const input = section.getByLabel('댓글 입력');
    const submit = section.getByRole('button', { name: '작성' });
    await expect(submit).toBeDisabled();
    await input.fill('   ');
    await expect(submit).toBeDisabled();
    await expect(input).toHaveAttribute('maxlength', '2000');
    await input.fill('가'.repeat(2001));
    await expect.poll(async () => (await input.inputValue()).length).toBeLessThanOrEqual(2000);
    await input.fill('');
    await expect(submit).toBeDisabled();
    await expect(page.getByTestId('trip-comment-list')).toHaveCount(0);
  });

  test('SHR-024 동행(test2)이 쓴 댓글은 소유자의 댓글 탭 재진입 시 보인다', async ({ page, browser }) => {
    test.skip(({ isMobile }) => isMobile, '데스크톱 전용(두 신원)');
    const title = uniqueTitle('024');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');
    await inviteCompanion(page, user2Email(), 'viewer');
    await expect(page.getByTestId('companion-list').getByRole('listitem')).toHaveCount(1);

    const user2 = await user2Context(browser);
    try {
      await gotoTrip(user2.page, id, title);
      await openTripTab(user2.page, '댓글');
      await openTripTab(page, '댓글');
      await expect(commentSection(page)).toContainText('아직 댓글이 없습니다.');

      // viewer도 댓글은 쓸 수 있다(create_trip_comment는 get_trip_for_user = 읽기 권한).
      const body = `[e2e] SHR-024 전파 ${Date.now()}`;
      await postComment(user2.page, body);

      // TripComments는 자체 fetch — realtime reload와 무관하므로 탭 재진입(remount)으로 갱신된다.
      await openTripTab(page, '일정');
      await openTripTab(page, '댓글');
      await expect(page.getByTestId('trip-comment-list')).toContainText(body);
      await shot(page, 'SHR-024', '01-comment-visible-after-reenter');

      await user2.page.getByTestId('trip-comment-list').getByRole('button', { name: '댓글 삭제' }).click();
      await expect(commentSection(user2.page)).toContainText('아직 댓글이 없습니다.');
    } finally {
      await user2.context.close();
    }
    await openTripTab(page, '동행');
    await companionSection(page).getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });

  test('SHR-033 동행(test2)의 댓글 — 작성자만 삭제 버튼, 소유자 화면엔 버튼 없음', async ({
    page,
    browser,
  }) => {
    test.skip(({ isMobile }) => isMobile, '데스크톱 전용(두 신원)');
    const title = uniqueTitle('033');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');
    await inviteCompanion(page, user2Email(), 'editor');
    await expect(page.getByTestId('companion-list').getByRole('listitem')).toHaveCount(1);

    const user2 = await user2Context(browser);
    try {
      await gotoTrip(user2.page, id, title);
      await openTripTab(user2.page, '댓글');
      const body = `[e2e] SHR-033 동행 댓글 ${Date.now()}`;
      await postComment(user2.page, body);
      await expect(
        user2.page.getByTestId('trip-comment-list').getByRole('button', { name: '댓글 삭제' }),
      ).toHaveCount(1);

      // 소유자가 쓴 댓글은 소유자 화면에서 삭제 가능, 동행 댓글은 버튼 없음(canDeleteComment=작성자만).
      await openTripTab(page, '댓글');
      const ownerBody = `[e2e] SHR-033 소유자 댓글 ${Date.now()}`;
      await postComment(page, ownerBody);
      const ownerList = page.getByTestId('trip-comment-list');
      await expect(ownerList).toContainText(body);
      await expect(ownerList.getByRole('listitem')).toHaveCount(2);
      await expect(ownerList.getByRole('button', { name: '댓글 삭제' })).toHaveCount(1);
      await expect(
        ownerList.getByRole('listitem').filter({ hasText: body }).getByRole('button', { name: '댓글 삭제' }),
      ).toHaveCount(0);
      await shot(page, 'SHR-033', '01-owner-delete-only-own');

      // 반대로 동행 화면에서도 소유자 댓글에는 삭제 버튼이 없다.
      await openTripTab(user2.page, '일정');
      await openTripTab(user2.page, '댓글');
      const user2List = user2.page.getByTestId('trip-comment-list');
      await expect(user2List).toContainText(ownerBody);
      await expect(user2List.getByRole('button', { name: '댓글 삭제' })).toHaveCount(1);

      await ownerList.getByRole('button', { name: '댓글 삭제' }).click();
      await expect(ownerList.getByRole('listitem')).toHaveCount(1);
      await user2List.getByRole('button', { name: '댓글 삭제' }).click();
      await expect(commentSection(user2.page)).toContainText('아직 댓글이 없습니다.');
    } finally {
      await user2.context.close();
    }
    await openTripTab(page, '동행');
    await companionSection(page).getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });
});
