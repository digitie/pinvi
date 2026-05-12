import type { Metadata } from "next";
import type { ReactNode } from "react";
import { QueryProvider } from "./shared/query-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "TripMate",
  description: "대한민국 국내 여행 계획을 지도, 일정, 알림으로 관리하는 TripMate.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
