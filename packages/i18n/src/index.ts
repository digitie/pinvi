import ko from '../messages/ko.json';

export const messages = { ko } as const;
export type Locale = keyof typeof messages;
export const defaultLocale: Locale = 'ko';
