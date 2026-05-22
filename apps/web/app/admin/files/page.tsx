"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  deleteAdminRustfsObject,
  fetchAdminMe,
  fetchAdminRustfsObjects,
  logoutAdmin,
  type AdminRustfsObjectQuery,
} from "../api";
import { FileUploadPanel, type AttachmentTarget } from "../../shared/file-upload-panel";
import { queryKeys } from "../../shared/query-keys";

const DEFAULT_LIMIT = 100;

export default function AdminFilesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [prefixInput, setPrefixInput] = useState("user-uploads/");
  const [submittedPrefix, setSubmittedPrefix] = useState("user-uploads/");
  const [targetMode, setTargetMode] = useState<"noticePlan" | "noticePoi">("noticePlan");
  const [noticePlanId, setNoticePlanId] = useState("");
  const [noticePoiId, setNoticePoiId] = useState("");
  const query = useMemo<AdminRustfsObjectQuery>(
    () => ({ prefix: submittedPrefix, limit: DEFAULT_LIMIT }),
    [submittedPrefix],
  );

  const adminMeQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: fetchAdminMe,
    retry: false,
  });
  const objectsQuery = useQuery({
    queryKey: queryKeys.admin.rustfsObjects(query),
    queryFn: () => fetchAdminRustfsObjects(query),
    retry: false,
  });
  const logoutMutation = useMutation({
    mutationFn: logoutAdmin,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.admin.root() });
      router.replace("/admin/login");
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteAdminRustfsObject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.rustfsObjects(query) });
    },
  });

  const target = useMemo<AttachmentTarget | null>(() => {
    const planId = noticePlanId.trim();
    const poiId = noticePoiId.trim();
    if (!planId) {
      return null;
    }
    if (targetMode === "noticePoi") {
      return poiId ? { kind: "noticePoi", planId, poiId } : null;
    }
    return { kind: "noticePlan", planId };
  }, [noticePlanId, noticePoiId, targetMode]);

  const uploadPurpose =
    targetMode === "noticePoi" ? "notice_poi_attachment" : "notice_plan_attachment";

  useEffect(() => {
    if (adminMeQuery.error) {
      router.replace("/admin/login");
    }
  }, [adminMeQuery.error, router]);

  function submitPrefix(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmittedPrefix(prefixInput.trim());
  }

  if (adminMeQuery.isPending) {
    return (
      <main className="min-h-screen bg-stone-100 p-6">
        <p className="text-sm font-bold text-stone-600">관리자 정보를 불러오는 중</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-stone-100 px-4 py-6 text-stone-900 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase text-teal-700">TripMate Admin</p>
            <h1 className="mt-1 text-2xl font-black">파일 관리</h1>
            <p className="mt-1 text-sm font-semibold text-stone-600">
              RustFS 객체와 공지 plan/poi 첨부 파일을 관리합니다.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2">
            <Link className="admin-top-button" href="/admin">
              데이터
            </Link>
            <Link className="admin-top-button" href="/admin/data">
              CRUD
            </Link>
            <Link className="admin-top-button" href="/admin/users">
              사용자
            </Link>
            <button className="admin-top-button" type="button" onClick={() => logoutMutation.mutate()}>
              로그아웃
            </button>
          </nav>
        </header>

        <section className="rounded-md border border-stone-300 bg-white p-4">
          <form className="grid gap-3 md:grid-cols-[1fr_auto]" onSubmit={submitPrefix}>
            <label className="grid gap-2 text-sm font-bold text-stone-700">
              RustFS prefix
              <input
                className="admin-input"
                value={prefixInput}
                onChange={(event) => setPrefixInput(event.target.value)}
                placeholder="user-uploads/"
              />
            </label>
            <button className="admin-top-button self-end" type="submit">
              조회
            </button>
          </form>
        </section>

        <section className="grid gap-4 rounded-md border border-stone-300 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-black">RustFS 객체</h2>
            <button
              className="admin-page-button"
              type="button"
              onClick={() => objectsQuery.refetch()}
            >
              새로고침
            </button>
          </div>
          <div className="overflow-x-auto rounded-md border border-stone-200">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead className="bg-stone-50">
                <tr>
                  <th className="admin-th">Key</th>
                  <th className="admin-th">Size</th>
                  <th className="admin-th">Last modified</th>
                  <th className="admin-th">Public</th>
                  <th className="admin-th">Action</th>
                </tr>
              </thead>
              <tbody>
                {objectsQuery.data?.objects.map((object) => (
                  <tr key={object.key} className="bg-white">
                    <td className="admin-td font-mono text-xs">{object.key}</td>
                    <td className="admin-td">{formatBytes(object.size)}</td>
                    <td className="admin-td">{formatDate(object.last_modified)}</td>
                    <td className="admin-td">
                      {object.public_url ? (
                        <a
                          className="font-bold text-teal-800"
                          href={object.public_url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          열기
                        </a>
                      ) : (
                        <span className="text-stone-400">없음</span>
                      )}
                    </td>
                    <td className="admin-td">
                      <button
                        className="admin-page-button"
                        type="button"
                        disabled={deleteMutation.isPending}
                        onClick={() => deleteMutation.mutate(object.key)}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
                {!objectsQuery.isPending && (objectsQuery.data?.objects.length ?? 0) === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm font-bold text-stone-500" colSpan={5}>
                      조회된 RustFS 객체가 없습니다.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {objectsQuery.error ? (
            <p className="text-sm font-bold text-red-700">{getErrorMessage(objectsQuery.error)}</p>
          ) : null}
        </section>

        <section className="grid gap-4 rounded-md border border-stone-300 bg-white p-4">
          <div>
            <h2 className="text-base font-black">공지 첨부 업로드</h2>
            <p className="mt-1 text-sm font-semibold text-stone-600">
              선택한 공지 plan 또는 POI에 여러 파일을 동시에 첨부합니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className={targetMode === "noticePlan" ? "admin-top-button border-teal-700" : "admin-top-button"}
              type="button"
              onClick={() => setTargetMode("noticePlan")}
            >
              공지 plan
            </button>
            <button
              className={targetMode === "noticePoi" ? "admin-top-button border-teal-700" : "admin-top-button"}
              type="button"
              onClick={() => setTargetMode("noticePoi")}
            >
              공지 POI
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-bold text-stone-700">
              Notice plan ID
              <input
                className="admin-input font-mono"
                value={noticePlanId}
                onChange={(event) => setNoticePlanId(event.target.value)}
              />
            </label>
            {targetMode === "noticePoi" ? (
              <label className="grid gap-2 text-sm font-bold text-stone-700">
                Notice POI ID
                <input
                  className="admin-input font-mono"
                  value={noticePoiId}
                  onChange={(event) => setNoticePoiId(event.target.value)}
                />
              </label>
            ) : null}
          </div>
          <FileUploadPanel
            title="파일 업로드"
            target={target}
            purpose={uploadPurpose}
            onUploaded={() => {
              void objectsQuery.refetch();
            }}
          />
        </section>
      </div>
    </main>
  );
}

function formatBytes(size: number | null): string {
  if (size === null) {
    return "-";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "RustFS 파일 정보를 불러오지 못했다.";
}
