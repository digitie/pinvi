/**
 * 공유 링크 토큰을 같은 탭의 sessionStorage에 잠시 둔다(#671).
 *
 * 로그인 복귀 경로(`/login?next=`·OAuth `return_to_path`)에는 토큰을 싣지 않고 `/shared/{tripId}`만
 * 싣는다. 로그인 뒤 그 경로(`app/shared/[tripId]/page.tsx`)가 여기서 토큰을 되찾아 공유 화면으로
 * 돌아간다. sessionStorage는 탭 단위이고 탭을 닫으면 사라진다 — 새 탭(`noopener`)으로는 넘어가지 않는다.
 */
const KEY_PREFIX = 'pinvi.sharedToken.';

export function stashSharedToken(tripId: string, token: string): void {
  if (!tripId || !token) return;
  try {
    window.sessionStorage.setItem(KEY_PREFIX + tripId, token);
  } catch {
    // 저장소를 못 쓰면(사생활 보호 모드 등) 로그인 뒤 원래 탭으로 돌아가라는 안내로 끝난다.
  }
}

export function readStashedSharedToken(tripId: string): string | null {
  if (!tripId) return null;
  try {
    return window.sessionStorage.getItem(KEY_PREFIX + tripId);
  } catch {
    return null;
  }
}
