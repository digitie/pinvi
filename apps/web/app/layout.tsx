import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TripMate',
  description: '한국 여행 계획·기록·공유 — v2',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
