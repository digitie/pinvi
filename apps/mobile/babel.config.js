// Expo + NativeWind babel preset. expo-router 진입은 babel-preset-expo가 처리한다.
module.exports = function (api) {
  api.cache(true);
  return {
    presets: [
      ['babel-preset-expo', { jsxImportSource: 'nativewind' }],
      'nativewind/babel',
    ],
  };
};
