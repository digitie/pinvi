"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AdminApiError, loginAdmin } from "../api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@ad.min");
  const [password, setPassword] = useState("admin");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      await loginAdmin(email, password);
      router.replace("/admin");
    } catch (error) {
      if (error instanceof AdminApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("관리자 로그인 처리 중 오류가 발생했다.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-svh bg-[#f5f1e8] text-stone-950">
      <section className="mx-auto grid min-h-svh w-full max-w-6xl grid-cols-1 lg:grid-cols-[0.92fr_0.72fr]">
        <div className="flex flex-col justify-between px-6 py-8 sm:px-10 lg:px-12">
          <Link className="text-sm font-bold text-teal-800" href="/">
            TripMate
          </Link>
          <div className="max-w-xl py-16">
            <p className="mb-5 text-sm font-bold text-amber-700">관리자 전용</p>
            <h1 className="mb-6 text-4xl font-black leading-tight text-stone-950 sm:text-5xl">
              ETL 데이터 운영 화면
            </h1>
            <p className="max-w-lg text-base leading-7 text-stone-600">
              수집된 공공데이터와 캐시 테이블을 조회하고, 데이터 적재 상태를 빠르게 확인하는
              내부 관리 진입점입니다.
            </p>
          </div>
          <p className="text-xs text-stone-500">일반 사용자 로그인은 별도 화면으로 분리한다.</p>
        </div>

        <div className="flex items-center bg-white px-6 py-10 shadow-[0_0_80px_rgba(28,25,23,0.1)] sm:px-10 lg:px-12">
          <form className="w-full" onSubmit={handleSubmit}>
            <div className="mb-8">
              <h2 className="mb-2 text-2xl font-black text-stone-950">로그인</h2>
              <p className="text-sm text-stone-500">기본 개발 계정은 문서 기준값을 사용한다.</p>
            </div>

            <label className="mb-5 block">
              <span className="mb-2 block text-sm font-bold text-stone-700">이메일</span>
              <input
                className="h-12 w-full rounded-md border border-stone-300 bg-white px-3 text-base outline-none transition focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
                type="email"
                value={email}
                autoComplete="username"
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>

            <label className="mb-6 block">
              <span className="mb-2 block text-sm font-bold text-stone-700">비밀번호</span>
              <input
                className="h-12 w-full rounded-md border border-stone-300 bg-white px-3 text-base outline-none transition focus:border-teal-700 focus:ring-4 focus:ring-teal-700/10"
                type="password"
                value={password}
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>

            {errorMessage ? (
              <p className="mb-5 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">
                {errorMessage}
              </p>
            ) : null}

            <button
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-teal-800 px-4 text-sm font-black text-white transition hover:bg-teal-900 disabled:cursor-not-allowed disabled:bg-stone-300"
              type="submit"
              disabled={isSubmitting}
            >
              <KeyIcon />
              {isSubmitting ? "확인 중" : "관리자 로그인"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function KeyIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M14.5 10.5a4 4 0 1 0-3 3.87L13 16h2v2h2v2h3v-3.5l-5.5-6Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}
