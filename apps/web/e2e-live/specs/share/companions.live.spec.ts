/**
 * SHR 동행 — 초대(기존 사용자=test2)/상태/권한(viewer·editor)/제거/검증/대기 초대(sink env).
 * 두 번째 신원은 일반 사용자 test2@test.com(PINVI_E2E_USER2_EMAIL/PASSWORD). 초대 메일·Telegram
 * 알림은 그 주소로만 간다(소유자 승인). 동행 목록에 이메일이 표시되므로 목록 스크린샷은 찍지 않는다.
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, shot } from '../../helpers/live';
import {
  companionSection,
  createShareLink,
  gotoTrip,
  inviteCompanion,
  openTripTab,
  requireEnv,
  shareSection,
  uniqueTitle,
  user2Context,
  user2Email,
} from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 동행 (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, '데스크톱 전용');

  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-025 기존 사용자(test2) 초대 → "참여" 상태, 역할 라벨, 제거', async ({ page }) => {
    const title = uniqueTitle('025');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');

    const section = companionSection(page);
    await expect(section.getByRole('heading', { name: '동반자 (0)' })).toBeVisible();
    await expect(section.getByRole('button', { name: '초대' })).toBeDisabled();
    await expect(section.getByLabel('권한').locator('option')).toHaveText([
      '편집자',
      '보기 전용',
      '공동 소유자',
    ]);

    await inviteCompanion(page, user2Email(), 'editor');
    const list = page.getByTestId('companion-list');
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(list).toContainText('편집자');
    await expect(list).toContainText('참여');
    await expect(list).not.toContainText('초대됨');
    await expect(section.getByRole('heading', { name: '동반자 (1)' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /^동행/ })).toContainText('1');
    await expect(section.getByLabel('이메일')).toHaveValue('');

    await list.getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
    await expect(section.getByRole('heading', { name: '동반자 (0)' })).toBeVisible();
  });

  test('SHR-026 초대 검증 — 본인 이메일 409, 중복 초대(대소문자 무시) 409', async ({ page }) => {
    const userEmail = requireEnv('PINVI_E2E_USER_EMAIL');
    const title = uniqueTitle('026');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');
    const section = companionSection(page);

    await inviteCompanion(page, userEmail, 'viewer');
    await expect(section.getByRole('alert')).toContainText('여행 소유자는 동반자로 초대할 수 없습니다');
    await expect(page.getByTestId('companion-list')).toHaveCount(0);

    await inviteCompanion(page, user2Email(), 'viewer');
    await expect(page.getByTestId('companion-list').getByRole('listitem')).toHaveCount(1);
    await inviteCompanion(page, user2Email().toUpperCase(), 'editor');
    await expect(section.getByRole('alert')).toContainText('이미 초대된 동반자입니다');
    await expect(page.getByTestId('companion-list').getByRole('listitem')).toHaveCount(1);

    await page.getByTestId('companion-list').getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });

  test('SHR-027 미가입 이메일 초대 → "초대됨"(대기) — sink 주소 env가 있을 때만', async ({ page }) => {
    const sink = process.env.PINVI_E2E_COMPANION_EMAIL;
    test.skip(!sink, 'PINVI_E2E_COMPANION_EMAIL(초대 메일 sink, 미가입 주소)이 없어 건너뜀');
    const title = uniqueTitle('027');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');

    await inviteCompanion(page, sink!, 'viewer');
    const list = page.getByTestId('companion-list');
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(list).toContainText('초대됨');
    await expect(list).toContainText('보기 전용');
    await list.getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });

  test('SHR-028 보기 전용 동행 — 열람 가능, 편집·공유 링크 생성은 거부, 관리 정보 비노출', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('028');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    await createShareLink(page);
    await openTripTab(page, '동행');
    await inviteCompanion(page, user2Email(), 'viewer');
    await expect(page.getByTestId('companion-list')).toContainText('보기 전용');

    const user2 = await user2Context(browser);
    try {
      await gotoTrip(user2.page, id, title);
      await expect(user2.page.getByTestId('trip-realtime-status')).toContainText('연결됨');

      // 관리 정보 비노출: viewer에게는 공유 링크 목록이 비어 있고 생성은 403.
      await openTripTab(user2.page, '공유');
      await expect(user2.page.getByTestId('share-link-list')).toHaveCount(0);
      await shareSection(user2.page).getByRole('button', { name: '링크 만들기' }).click();
      await expect(shareSection(user2.page).getByRole('alert')).toContainText(
        '여행 소유자만 수행할 수 있습니다',
      );
      await expect(user2.page.getByTestId('new-share-url')).toHaveCount(0);

      // 편집 시도 → 403 메시지가 다이얼로그 안에 표시된다.
      await user2.page.getByRole('button', { name: '편집' }).first().click();
      await user2.page.locator('#trip-edit-title').fill(`${title} viewer-edit`);
      await user2.page.getByTestId('trip-edit-save').click();
      await expect(user2.page.getByTestId('trip-edit-dialog').getByRole('alert')).toContainText('이 여행을 편집할 권한이 없습니다');
      await shot(user2.page, 'SHR-028', '01-viewer-edit-denied');
      await expect(user2.page.getByRole('heading', { name: title }).first()).toBeVisible();

      // 동행 탭: viewer에게는 이메일(PII)이 가려진다(include_management=False).
      await openTripTab(user2.page, '동행');
      await expect(user2.page.getByTestId('companion-list')).not.toContainText(user2Email());
    } finally {
      await user2.context.close();
    }
    await openTripTab(page, '동행');
    await page.getByTestId('companion-list').getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });

  test('SHR-029 편집자 동행 — 제목 편집 가능, 공유 링크·초대는 여전히 소유자만', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('029');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');
    await inviteCompanion(page, user2Email(), 'editor');
    await expect(page.getByTestId('companion-list')).toContainText('편집자');

    const user2 = await user2Context(browser);
    try {
      await gotoTrip(user2.page, id, title);
      const edited = `${title} edited-by-companion`;
      await user2.page.getByRole('button', { name: '편집' }).first().click();
      await user2.page.locator('#trip-edit-title').fill(edited);
      await user2.page.getByTestId('trip-edit-save').click();
      await expect(user2.page.getByRole('heading', { name: edited }).first()).toBeVisible();
      // 소유자 화면은 realtime(trip.updated)로 갱신된다.
      await expect(page.getByRole('heading', { name: edited }).first()).toBeVisible();

      await openTripTab(user2.page, '공유');
      await shareSection(user2.page).getByRole('button', { name: '링크 만들기' }).click();
      await expect(shareSection(user2.page).getByRole('alert')).toContainText(
        '여행 소유자만 수행할 수 있습니다',
      );
      // 동행 초대/제거도 소유자 전용 — 소유자 검사가 이메일 검증보다 먼저이므로 기존 주소로 시도한다.
      await openTripTab(user2.page, '동행');
      await inviteCompanion(user2.page, requireEnv('PINVI_E2E_USER_EMAIL'), 'viewer');
      await expect(companionSection(user2.page).getByRole('alert')).toContainText(
        '여행 소유자만 수행할 수 있습니다',
      );
    } finally {
      await user2.context.close();
    }
    await openTripTab(page, '동행');
    await page.getByTestId('companion-list').getByRole('button', { name: '동반자 제거' }).click();
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
  });

  test('SHR-030 열람 중인 동행을 제거하면 그 화면은 권한 오류로 전환된다', async ({ page, browser }) => {
    const title = uniqueTitle('030');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '동행');
    await inviteCompanion(page, user2Email(), 'viewer');

    const user2 = await user2Context(browser);
    try {
      await gotoTrip(user2.page, id, title);
      await expect(user2.page.getByTestId('trip-realtime-status')).toContainText('연결됨');

      await page.getByTestId('companion-list').getByRole('button', { name: '동반자 제거' }).click();
      await expect(page.getByTestId('companion-list')).toHaveCount(0);

      // trip.member_changed → reload → 403 → 상세 오류. (WS가 먼저 끊기면 권한 상실 배너.)
      const errorOrBanner = user2.page
        .getByTestId('trip-detail-error')
        .or(user2.page.getByTestId('trip-realtime-permission-lost'));
      await expect(errorOrBanner.first()).toBeVisible({ timeout: 20_000 });
      await user2.page.reload();
      await expect(user2.page.getByTestId('trip-detail-error')).toContainText(
        '이 여행에 대한 권한이 없습니다',
      );
      await shot(user2.page, 'SHR-030', '01-removed-companion');
    } finally {
      await user2.context.close();
    }
  });
});
