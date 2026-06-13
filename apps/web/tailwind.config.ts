import type { Config } from 'tailwindcss';
import preset from '@pinvi/design-tokens/tailwind-preset';

const config: Config = {
  presets: [preset as Partial<Config>],
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
