import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TripMate",
  description: "대한민국 국내 여행 계획을 지도, 일정, 알림으로 관리하는 TripMate.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
