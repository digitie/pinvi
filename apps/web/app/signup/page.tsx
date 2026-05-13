"use client";

import Image from "next/image";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import { registerUser, type RegisterUserInput } from "./api";

const genderOptions = [
  { value: "", label: "선택 안 함" },
  { value: "female", label: "여성" },
  { value: "male", label: "남성" },
  { value: "non_binary", label: "논바이너리" },
  { value: "no_answer", label: "응답하지 않음" },
];

const signupFormSchema = z.object({
  email: z.string().trim().email("이메일 형식을 확인해 주세요."),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다.").max(128),
  nickname: z.string().trim().min(1, "닉네임을 입력해 주세요.").max(80),
  name: z.string().trim().min(1, "이름을 입력해 주세요.").max(80),
  birthYearMonth: z
    .string()
    .regex(/^[0-9]{6}$/, "생년월은 YYYYMM 6자리 숫자로 입력해 주세요.")
    .or(z.literal("")),
  gender: z.enum(["", "female", "male", "non_binary", "no_answer"]),
  residenceSigunguCode: z
    .string()
    .regex(/^[0-9]{10}$/, "거주지 코드는 10자리 숫자로 입력해 주세요.")
    .or(z.literal("")),
  tosAgreed: z.boolean().refine((value) => value, "Terms consent is required."),
  privacyAgreed: z.boolean().refine((value) => value, "Privacy consent is required."),
  demographicUseAgreed: z.boolean(),
  locationUseAgreed: z.boolean(),
  marketingAgreed: z.boolean(),
});

type SignupFormValues = z.infer<typeof signupFormSchema>;

export default function SignupPage() {
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupFormSchema),
    defaultValues: {
      email: "",
      password: "",
      nickname: "",
      name: "",
      birthYearMonth: "",
      gender: "",
      residenceSigunguCode: "",
      tosAgreed: false,
      privacyAgreed: false,
      demographicUseAgreed: false,
      locationUseAgreed: false,
      marketingAgreed: false,
    },
  });

  const signupMutation = useMutation({
    mutationFn: (input: RegisterUserInput) => registerUser(input),
    onSuccess: (_payload, variables) => {
      reset({
        email: variables.email,
        password: "",
        nickname: variables.nickname,
        name: variables.name,
        birthYearMonth: variables.birth_year_month ?? "",
        gender: variables.gender ?? "",
        residenceSigunguCode: variables.residence_sigungu_code ?? "",
        tosAgreed: variables.tos_agreed,
        privacyAgreed: variables.privacy_agreed,
        demographicUseAgreed: variables.demographic_use_agreed,
        locationUseAgreed: variables.location_use_agreed,
        marketingAgreed: variables.marketing_agreed,
      });
    },
  });

  function submitSignup(values: SignupFormValues) {
    signupMutation.reset();
    signupMutation.mutate({
      email: values.email,
      password: values.password,
      nickname: values.nickname,
      name: values.name,
      birth_year_month: normalizeOptionalValue(values.birthYearMonth),
      gender: normalizeOptionalValue(values.gender) as RegisterUserInput["gender"],
      residence_sigungu_code: normalizeOptionalValue(values.residenceSigunguCode),
      tos_agreed: values.tosAgreed,
      privacy_agreed: values.privacyAgreed,
      demographic_use_agreed: values.demographicUseAgreed,
      location_use_agreed: values.locationUseAgreed,
      marketing_agreed: values.marketingAgreed,
      consent_version: "2026-05-13",
    });
  }

  const createdUser = signupMutation.data?.user ?? null;
  const errorMessage = signupMutation.error
    ? getErrorMessage(signupMutation.error, "가입 요청을 처리하지 못했다.")
    : null;

  return (
    <main className="min-h-svh bg-white text-[#222222]">
      <section className="mx-auto grid min-h-svh w-full max-w-[1440px] grid-cols-1 lg:grid-cols-[minmax(360px,0.72fr)_minmax(520px,1fr)]">
        <aside className="flex min-h-[34svh] flex-col justify-between border-b border-[#ebebeb] bg-[#fff7f9] px-5 py-8 sm:px-8 lg:min-h-svh lg:border-b-0 lg:border-r lg:px-12">
          <Link className="inline-flex items-center gap-2 text-sm font-semibold" href="/">
            <span className="flex size-8 items-center justify-center rounded-full bg-[#ff385c]">
              <Image alt="" height={16} src="/maki/marker.svg" width={16} />
            </span>
            TripMate
          </Link>
          <div className="py-10 lg:py-16">
            <p className="text-sm font-semibold text-[#ff385c]">Signup</p>
            <h1 className="mt-3 !mb-0 max-w-md !text-2xl font-semibold !leading-tight tracking-normal sm:!text-3xl">
              여행을 저장할 계정을 만듭니다.
            </h1>
            <p className="mt-4 max-w-md text-base leading-7 text-[#6a6a6a]">
              일정과 장소를 한곳에 모아두세요.
            </p>
          </div>
          <Link className="inline-flex items-center gap-2 text-sm font-semibold text-[#222222] underline underline-offset-4" href="/login">
            이미 계정이 있어요
            <ArrowRightIcon />
          </Link>
        </aside>

        <section className="flex items-center bg-white px-5 py-10 sm:px-8 lg:px-14">
          <form className="w-full max-w-[680px]" onSubmit={handleSubmit(submitSignup)}>
            <div className="mb-8">
              <h2 className="text-[1.75rem] font-semibold tracking-normal">계정 정보</h2>
              <p className="mt-2 text-sm leading-6 text-[#6a6a6a]">필수 정보부터 빠르게.</p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="block md:col-span-2">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">이메일</span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  type="email"
                  autoComplete="email"
                  aria-invalid={errors.email ? "true" : "false"}
                  {...register("email")}
                />
                {errors.email ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.email.message}
                  </span>
                ) : null}
              </label>

              <label className="block md:col-span-2">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">비밀번호</span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={errors.password ? "true" : "false"}
                  {...register("password")}
                />
                {errors.password ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.password.message}
                  </span>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">닉네임</span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  maxLength={80}
                  aria-invalid={errors.nickname ? "true" : "false"}
                  {...register("nickname")}
                />
                {errors.nickname ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.nickname.message}
                  </span>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">이름</span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  maxLength={80}
                  aria-invalid={errors.name ? "true" : "false"}
                  {...register("name")}
                />
                {errors.name ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.name.message}
                  </span>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">생년월</span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  placeholder="YYYYMM"
                  maxLength={6}
                  aria-invalid={errors.birthYearMonth ? "true" : "false"}
                  {...register("birthYearMonth")}
                />
                {errors.birthYearMonth ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.birthYearMonth.message}
                  </span>
                ) : null}
              </label>

              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">성별</span>
                <select
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  {...register("gender")}
                >
                  {genderOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block md:col-span-2">
                <span className="mb-2 block text-sm font-semibold text-[#222222]">
                  거주지 시군구 코드
                </span>
                <input
                  className="h-14 w-full rounded-lg border border-[#dddddd] bg-white px-4 text-base outline-none transition focus:border-[#222222]"
                  inputMode="numeric"
                  pattern="[0-9]{10}"
                  placeholder="예: 1111000000"
                  maxLength={10}
                  aria-invalid={errors.residenceSigunguCode ? "true" : "false"}
                  {...register("residenceSigunguCode")}
                />
                {errors.residenceSigunguCode ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.residenceSigunguCode.message}
                  </span>
                ) : null}
              </label>

              <fieldset className="md:col-span-2 rounded-lg border border-[#dddddd] p-4">
                <legend className="px-1 text-sm font-semibold text-[#222222]">Consent</legend>
                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  <ConsentCheckbox
                    label="Terms"
                    registration={register("tosAgreed")}
                    required
                  />
                  <ConsentCheckbox
                    label="Privacy"
                    registration={register("privacyAgreed")}
                    required
                  />
                  <ConsentCheckbox
                    label="Demographic use"
                    registration={register("demographicUseAgreed")}
                  />
                  <ConsentCheckbox
                    label="Location use"
                    registration={register("locationUseAgreed")}
                  />
                  <ConsentCheckbox
                    label="Marketing"
                    registration={register("marketingAgreed")}
                  />
                </div>
                {errors.tosAgreed ? (
                  <span className="mt-3 block text-sm font-semibold text-[#c13515]">
                    {errors.tosAgreed.message}
                  </span>
                ) : null}
                {errors.privacyAgreed ? (
                  <span className="mt-2 block text-sm font-semibold text-[#c13515]">
                    {errors.privacyAgreed.message}
                  </span>
                ) : null}
              </fieldset>
            </div>

            {errorMessage ? (
              <p className="mt-5 rounded-lg border border-[#f2b8aa] bg-[#fff8f6] px-4 py-3 text-sm font-semibold text-[#c13515]">
                {errorMessage}
              </p>
            ) : null}

            {createdUser ? (
              <div className="mt-5 rounded-lg border border-[#dddddd] bg-[#f7f7f7] px-4 py-3 text-sm text-[#3f3f3f]">
                <p className="font-semibold text-[#222222]">{createdUser.email}</p>
                <p className="mt-1">
                  상태: {createdUser.account_status} · 프로필: {createdUser.status} · 역할:{" "}
                  {createdUser.system_role}
                </p>
                {createdUser.email_verification_required ? (
                  <p className="mt-1">
                    {createdUser.verification_email_dispatched
                      ? "인증 메일을 확인해 가입을 완료해 주세요."
                      : "이메일 전송 설정이 완료되면 인증 메일이 발송됩니다."}
                  </p>
                ) : null}
              </div>
            ) : null}

            <button
              className="mt-6 inline-flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#ff385c] px-5 text-base font-semibold text-white transition active:bg-[#e00b41] disabled:cursor-not-allowed disabled:bg-[#ffd1da]"
              type="submit"
              disabled={signupMutation.isPending}
            >
              <UserPlusIcon />
              {signupMutation.isPending ? "가입 처리 중" : "가입하기"}
            </button>
          </form>
        </section>
      </section>
    </main>
  );
}

function ConsentCheckbox({
  label,
  registration,
  required = false,
}: {
  label: string;
  registration: UseFormRegisterReturn;
  required?: boolean;
}) {
  return (
    <label className="flex min-h-10 items-center gap-3 rounded-md border border-[#eeeeee] px-3 py-2 text-sm font-semibold text-[#222222]">
      <input
        className="size-4 accent-[#ff385c]"
        type="checkbox"
        aria-required={required ? "true" : "false"}
        {...registration}
      />
      <span>{required ? `${label} *` : label}</span>
    </label>
  );
}

function normalizeOptionalValue(value: string): string | null {
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function UserPlusIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" stroke="currentColor" strokeWidth="2" />
      <path d="M19 8v6M22 11h-6" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}
