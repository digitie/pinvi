// Expo 표준 flat config(https://docs.expo.dev/guides/using-eslint/) — SDK 56 정합
// `eslint-config-expo@~56`. `expo lint`가 아니라 `eslint` 바이너리를 직접 호출한다(설정 부재 시
// expo CLI가 CI에서 자동 설치·파일 생성하는 mutating fallback을 피하기 위함, issue #215).
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', '.expo/*', 'vendor/*', 'node_modules/*'],
  },
]);
