"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { Suspense, useEffect } from "react";
import { verifyEmail } from "./api";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerifyEmailShell statusText="이메일 인증을 준비하는 중" />}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const mutation = useMutation({
    mutationFn: verifyEmail,
  });
  const { isIdle, mutate } = mutation;

  useEffect(() => {
    if (token && isIdle) {
      mutate(token);
    }
  }, [isIdle, mutate, token]);

  if (!token) {
    return (
      <VerifyEmailShell
        statusText="인증 링크가 올바르지 않습니다."
        description="이메일에 포함된 링크를 다시 열어 주세요."
      />
    );
  }

  if (mutation.isPending || mutation.isIdle) {
    return <VerifyEmailShell statusText="이메일을 인증하는 중" />;
  }

  if (mutation.isError) {
    return (
      <VerifyEmailShell
        statusText="이메일 인증에 실패했습니다."
        description={getErrorMessage(mutation.error, "인증 링크가 만료되었거나 이미 사용되었습니다.")}
      />
    );
  }

  const user = mutation.data.user;
  const displayName = user.nickname ?? user.display_name ?? user.name ?? user.email;
  return (
    <VerifyEmailShell
      statusText={`${displayName}님, 이메일 인증이 완료되었습니다.`}
      description="이제 TripMate에 로그인할 수 있습니다."
      actionHref="/login"
      actionLabel="로그인하기"
    />
  );
}

function VerifyEmailShell({
  actionHref,
  actionLabel,
  description,
  statusText,
}: {
  actionHref?: string;
  actionLabel?: string;
  description?: string;
  statusText: string;
}) {
  return (
    <main className="flex min-h-svh items-center justify-center bg-white px-5 text-[#222222]">
      <section className="w-full max-w-[440px]">
        <Link className="inline-flex items-center gap-2 text-sm font-semibold" href="/">
          <span className="flex size-8 items-center justify-center rounded-full bg-[#ff385c] text-white">
            T
          </span>
          TripMate
        </Link>
        <div className="mt-10 border-l-4 border-[#ff385c] pl-5">
          <p className="text-sm font-semibold text-[#ff385c]">Email verification</p>
          <h1 className="mt-3 text-2xl font-semibold leading-tight tracking-normal">{statusText}</h1>
          {description ? <p className="mt-4 text-sm leading-6 text-[#6a6a6a]">{description}</p> : null}
          {actionHref && actionLabel ? (
            <Link
              className="mt-6 inline-flex h-11 items-center justify-center rounded-lg bg-[#ff385c] px-5 text-sm font-semibold text-white"
              href={actionHref}
            >
              {actionLabel}
            </Link>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
