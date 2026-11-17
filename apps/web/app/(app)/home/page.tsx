import { PersonalHome } from '@/components/home/PersonalHome';

/* 로그인 사용자의 개인 홈 — 워드마크(로고)와 '홈' 메뉴의 목적지.
 * 로그인하지 않았으면 API 401 → apiClient가 `/login?next=/home`으로 보낸다(lib/api.ts).
 */
export default function HomePage() {
  return <PersonalHome />;
}
