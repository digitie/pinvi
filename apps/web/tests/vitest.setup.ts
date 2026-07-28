// RTL matchers (toBeInTheDocument 등). vitest 4 마이그레이션에서 node 환경을 제거하고
// 모든 테스트를 jsdom 단일 환경으로 통일했으므로, 이 setup은 전 테스트에 matcher만 등록한다.
import '@testing-library/jest-dom/vitest';
