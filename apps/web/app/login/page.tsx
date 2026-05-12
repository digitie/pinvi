"use client";

import Image from "next/image";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FormEvent } from "react";
import { queryKeys } from "../shared/query-keys";
import { useLoginPageStore } from "../shared/stores";
import { fetchFestivalMonthly, loginUser, type FestivalSummary } from "./api";

const monthLabels = [
  "1월",
  "2월",
  "3월",
  "4월",
  "5월",
  "6월",
  "7월",
  "8월",
  "9월",
  "10월",
  "11월",
  "12월",
];

const fallbackFestivals: FestivalSummary[] = [
  {
    id: "sample-1",
    source_record_id: "sample-1",
    festival_name: "이천도자기축제",
    venue_name: "이천도자예술마을",
    event_start_date: "2026-04-24",
    event_end_date: "2026-05-05",
    event_status: "ongoing",
    road_address: "경기도 이천시 신둔면 도자예술로5번길 109",
    jibun_address: null,
    sigungu_code: "4150000000",
    sido_code: "4100000000",
    longitude: null,
    latitude: null,
    homepage_url: null,
  },
  {
    id: "sample-2",
    source_record_id: "sample-2",
    festival_name: "진해군항제",
    venue_name: "중원로터리 및 진해루 일원",
    event_start_date: "2026-03-27",
    event_end_date: "2026-04-05",
    event_status: "ended",
    road_address: "경상남도 창원시 진해구 진해대로 649",
    jibun_address: null,
    sigungu_code: "4812900000",
    sido_code: "4800000000",
    longitude: null,
    latitude: null,
    homepage_url: null,
  },
];

export default function LoginPage() {
  const {
    clearLoginFeedback,
    email,
    loginMessage,
    password,
    resetLoginPassword,
    selectedMonth,
    setLoginField,
    setLoginMessage,
    setSelectedMonth,
    year,
  } = useLoginPageStore();

  const festivalQuery = useQuery({
    queryKey: queryKeys.public.festivalMonthly(year, selectedMonth),
    queryFn: () => fetchFestivalMonthly(year, selectedMonth),
  });

  const loginMutation = useMutation({
    mutationFn: () => loginUser(email, password),
    onMutate: () => {
      clearLoginFeedback();
    },
    onSuccess: (payload) => {
      const displayName =
        payload.user.nickname ?? payload.user.display_name ?? payload.user.name ?? payload.user.email;
      setLoginMessage(`${displayName}님, 로그인되었습니다.`);
      resetLoginPassword();
    },
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loginMutation.reset();
    loginMutation.mutate();
  }

  const festivalPayload = festivalQuery.data ?? null;
  const festivalError = null;
  const isFestivalLoading = festivalQuery.isPending;
  const loginError = loginMutation.error
    ? getErrorMessage(loginMutation.error, "로그인 요청에 실패했다.")
    : null;
  const festivals = festivalPayload?.festivals.length ? festivalPayload.festivals : fallbackFestivals;
  const monthSummaries =
    festivalPayload?.months ??
    Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      count: index + 1 === selectedMonth ? fallbackFestivals.length : 0,
    }));
  const season = seasonForMonth(selectedMonth);

  return (
    <main className="min-h-svh bg-white text-[#222222]">
      <section className="mx-auto grid min-h-svh w-full max-w-[1440px] grid-cols-1 lg:grid-cols-[minmax(420px,0.82fr)_minmax(420px,1fr)]">
        <section
          className={`order-2 flex min-h-[56svh] flex-col px-4 py-5 sm:px-6 sm:py-8 lg:order-1 lg:min-h-svh lg:px-8 ${season.surface}`}
        >
          <div className="flex items-center justify-between gap-4">
            <Link className="inline-flex items-center gap-2 text-sm font-semibold" href="/">
              <span className="flex size-8 items-center justify-center rounded-full bg-[#ff385c]">
                <Image alt="" height={16} src="/maki/marker.svg" width={16} />
              </span>
              TripMate
            </Link>
            <button
              aria-label="축제 검색"
              className="flex size-10 items-center justify-center rounded-full border border-[#dddddd] bg-white text-[#222222] transition hover:border-[#222222]"
              type="button"
            >
              <SearchIcon />
            </button>
          </div>

          <div className="mt-8">
            <p className="text-sm font-semibold text-[#ff385c]">Festival</p>
            <h1 className="mt-2 !mb-0 !max-w-none !text-2xl font-semibold !leading-tight tracking-normal sm:!text-3xl">
              {selectedMonth}월 국내 축제
            </h1>
          </div>

          <div className="mt-5 overflow-x-auto pb-2">
            <div className="flex min-w-max gap-2">
              {monthLabels.map((label, index) => {
                const month = index + 1;
                const count = monthSummaries.find((item) => item.month === month)?.count ?? 0;
                const isSelected = selectedMonth === month;
                return (
                  <button
                    className={`h-10 rounded-full border px-4 text-sm font-semibold transition ${
                      isSelected
                        ? "border-[#222222] bg-[#222222] text-white"
                        : "border-[#dddddd] bg-white text-[#6a6a6a] hover:border-[#222222] hover:text-[#222222]"
                    }`}
                    key={month}
                    type="button"
                    onClick={() => setSelectedMonth(month)}
                  >
                    {label}
                    <span className="ml-1 text-xs opacity-75">({count})</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-3 flex flex-1 flex-col gap-3 overflow-y-auto pr-1">
            {festivals.slice(0, 6).map((festival) => (
              <article
                className="grid min-h-[108px] grid-cols-[88px_minmax(0,1fr)] gap-3 rounded-[14px] border border-[#dddddd] bg-white p-3 shadow-[rgba(0,0,0,0.02)_0_0_0_1px,rgba(0,0,0,0.04)_0_2px_6px,rgba(0,0,0,0.10)_0_4px_8px] transition hover:border-[#c1c1c1]"
                key={festival.id}
              >
                <div className={`relative flex min-h-[84px] items-center justify-center overflow-hidden rounded-lg ${season.thumbnail}`}>
                  <div className="absolute left-2 top-2 h-6 w-10 rounded-full bg-white/75" />
                  <div className="absolute bottom-2 right-2 size-8 rounded-full bg-white/60" />
                  <span className="flex size-11 items-center justify-center rounded-full bg-white shadow-[rgba(0,0,0,0.08)_0_2px_8px]">
                    <Image alt="" height={20} src="/maki/music.svg" width={20} />
                  </span>
                </div>
                <div className="flex min-w-0 flex-col">
                  <div className="flex min-w-0 items-start gap-2">
                    <span className={`mt-0.5 shrink-0 rounded-full px-2 py-1 text-[11px] font-semibold ${season.badge}`}>
                      {selectedMonth}월
                    </span>
                    <h2 className="min-w-0 text-[15px] font-semibold leading-5 tracking-normal">
                      {festival.festival_name}
                    </h2>
                  </div>
                  <p className="mt-2 text-[13px] leading-5 text-[#3f3f3f]">
                    기간: {formatDateRange(festival.event_start_date, festival.event_end_date)}
                  </p>
                  <p className="line-clamp-2 text-[13px] leading-5 text-[#3f3f3f]">
                    위치: {festival.venue_name ?? festival.road_address ?? festival.jibun_address ?? "장소 확인 중"}
                  </p>
                  <p className="mt-auto pt-1 text-right text-[12px] text-[#929292]">
                    {formatShortDate(festival.event_start_date ?? festival.event_end_date)}
                  </p>
                </div>
              </article>
            ))}
          </div>

          {festivalError ? (
            <p className="mt-5 text-sm font-semibold text-[#c13515]">{festivalError}</p>
          ) : null}
          {isFestivalLoading ? (
            <p className="mt-5 text-sm font-semibold text-[#6a6a6a]">축제 정보를 불러오는 중</p>
          ) : null}
        </section>

        <section className="order-1 flex min-h-[44svh] items-center justify-center px-5 py-8 sm:px-8 lg:order-2 lg:min-h-svh lg:px-12">
          <form className="w-full max-w-[420px]" onSubmit={handleSubmit}>
            <div className="mb-8">
              <p className="text-sm font-semibold text-[#ff385c]">Login</p>
              <h2 className="mt-3 text-[2rem] font-semibold tracking-normal">다시 여행을 이어갑니다.</h2>
            </div>

            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#222222]">이메일</span>
              <input
                className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222] focus:ring-2 focus:ring-[#222222]"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setLoginField("email", event.target.value)}
                required
              />
            </label>

            <label className="mt-4 block">
              <span className="mb-2 block text-sm font-semibold text-[#222222]">비밀번호</span>
              <input
                className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222] focus:ring-2 focus:ring-[#222222]"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setLoginField("password", event.target.value)}
                required
              />
            </label>

            {loginMessage ? (
              <p className="mt-4 rounded-lg border border-[#dddddd] bg-[#f7f7f7] px-4 py-3 text-sm font-semibold text-[#6a6a6a]">
                {loginMessage}
              </p>
            ) : null}
            {loginError ? (
              <p className="mt-4 rounded-lg border border-[#f4b8a8] bg-[#fff4ef] px-4 py-3 text-sm font-semibold text-[#c13515]">
                {loginError}
              </p>
            ) : null}

            <button
              className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-lg bg-[#ff385c] px-5 text-base font-semibold text-white transition active:bg-[#e00b41] disabled:cursor-not-allowed disabled:opacity-60"
              type="submit"
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? "확인 중" : "로그인"}
            </button>

            <div className="mt-5 flex items-center justify-between gap-3 text-sm font-semibold text-[#222222]">
              <button className="underline underline-offset-4" type="button">
                비밀번호 찾기
              </button>
              <Link className="underline underline-offset-4" href="/signup">
                회원가입
              </Link>
            </div>
          </form>
        </section>
      </section>
    </main>
  );
}

function seasonForMonth(month: number): {
  surface: string;
  thumbnail: string;
  badge: string;
} {
  if ([3, 4, 5].includes(month)) {
    return {
      surface: "bg-[#fff7f9]",
      thumbnail: "bg-[linear-gradient(135deg,#ffe4ea,#ff9db0)]",
      badge: "bg-[#fff1a8] text-[#222222]",
    };
  }
  if ([6, 7, 8].includes(month)) {
    return {
      surface: "bg-[#fff4eb]",
      thumbnail: "bg-[linear-gradient(135deg,#fff1d6,#ff8a3d)]",
      badge: "bg-[#ffe2c2] text-[#7a3100]",
    };
  }
  if ([9, 10, 11].includes(month)) {
    return {
      surface: "bg-[#fff8e8]",
      thumbnail: "bg-[linear-gradient(135deg,#fff0bc,#d97706)]",
      badge: "bg-[#ffe8a3] text-[#614000]",
    };
  }
  return {
    surface: "bg-[#f2f7ff]",
    thumbnail: "bg-[linear-gradient(135deg,#edf6ff,#8fb7ff)]",
    badge: "bg-[#dbeafe] text-[#1e3a8a]",
  };
}

function formatDateRange(start: string | null, end: string | null): string {
  if (!start && !end) {
    return "일정 확인 중";
  }
  if (start && end && start !== end) {
    return `${formatDate(start)} - ${formatDate(end)}`;
  }
  return formatDate(start ?? end ?? "");
}

function formatDate(value: string): string {
  const [, month, day] = value.split("-");
  if (!month || !day) {
    return value;
  }
  return `${Number(month)}월 ${Number(day)}일`;
}

function formatShortDate(value: string | null): string {
  if (!value) {
    return "일정 확인 중";
  }
  return value.replaceAll("-", ".");
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="m20 20-4.2-4.2M10.8 18a7.2 7.2 0 1 0 0-14.4 7.2 7.2 0 0 0 0 14.4Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2"
      />
    </svg>
  );
}
