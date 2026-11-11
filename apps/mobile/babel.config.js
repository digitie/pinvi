// NativeWind5는 Metro 통합을 사용한다. Expo Router의 Babel 설정은 유지한다.
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
  };
};
