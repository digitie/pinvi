"use client";

import { ChangeEvent, useMemo, useState } from "react";
import { fetchApi } from "./api-base";

export type AttachmentUploadPurpose =
  | "plan_attachment"
  | "poi_attachment"
  | "notice_plan_attachment"
  | "notice_poi_attachment";

export type AttachmentTarget =
  | { kind: "trip"; tripId: string }
  | { kind: "tripPoi"; tripId: string; poiId: string }
  | { kind: "noticePlan"; planId: string }
  | { kind: "noticePoi"; planId: string; poiId: string };

type StoredAttachment = {
  id: string;
  original_filename: string;
  storage_key: string;
  public_url: string | null;
};

type UploadRow = {
  id: string;
  filename: string;
  progress: number;
  status: "queued" | "presigning" | "uploading" | "finalizing" | "done" | "failed";
  error: string | null;
  attachment: StoredAttachment | null;
};

type UploadUrlResponse = {
  bucket: string;
  storage_key: string;
  upload_url: string;
  headers: Record<string, string>;
  public_url: string | null;
};

type FileUploadPanelProps = {
  title: string;
  target: AttachmentTarget | null;
  purpose: AttachmentUploadPurpose;
  disabled?: boolean;
  onUploaded?: (attachment: StoredAttachment) => void;
};

export function FileUploadPanel({
  title,
  target,
  purpose,
  disabled = false,
  onUploaded,
}: FileUploadPanelProps) {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const canUpload = Boolean(target) && !disabled;
  const acceptedTypes = useMemo(
    () => ["image/jpeg", "image/png", "image/webp", "image/gif", "video/mp4", "application/pdf"],
    [],
  );

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!target || files.length === 0) {
      return;
    }
    const uploadRows = files.map((file) => newUploadRow(file.name));
    setRows((current) => [...uploadRows, ...current]);
    for (const [index, file] of files.entries()) {
      void uploadOne(file, uploadRows[index], target);
    }
  }

  async function uploadOne(file: File, row: UploadRow, uploadTarget: AttachmentTarget) {
    try {
      updateRow(row.id, { status: "presigning", progress: 0 });
      const upload = await createUploadUrl(file, purpose);
      updateRow(row.id, { status: "uploading", progress: 1 });
      await putFileWithProgress(upload, file, (progress) => {
        updateRow(row.id, { progress, status: "uploading" });
      });
      updateRow(row.id, { status: "finalizing", progress: 100 });
      const attachment = await createAttachment(uploadTarget, {
        bucket: upload.bucket,
        storage_key: upload.storage_key,
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        byte_size: file.size,
        public_url: upload.public_url,
        role: file.type.startsWith("image/") ? "image" : "attachment",
      });
      updateRow(row.id, { status: "done", progress: 100, attachment });
      onUploaded?.(attachment);
    } catch (error) {
      updateRow(row.id, {
        status: "failed",
        error: error instanceof Error ? error.message : "파일 업로드에 실패했다.",
      });
    }
  }

  function updateRow(rowId: string, patch: Partial<UploadRow>) {
    setRows((current) => current.map((row) => (row.id === rowId ? { ...row, ...patch } : row)));
  }

  return (
    <section className="rounded-md border border-stone-300 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-black text-stone-900">{title}</h2>
        <label className="admin-top-button cursor-pointer">
          파일 선택
          <input
            className="sr-only"
            type="file"
            accept={acceptedTypes.join(",")}
            multiple
            disabled={!canUpload}
            onChange={handleFiles}
          />
        </label>
      </div>
      {!canUpload ? (
        <p className="mt-3 text-sm font-semibold text-stone-500">첨부 대상을 먼저 지정하세요.</p>
      ) : null}
      <div className="mt-4 grid gap-3">
        {rows.map((row) => (
          <article key={row.id} className="rounded-md border border-stone-200 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong className="min-w-0 truncate text-sm text-stone-900">{row.filename}</strong>
              <span className="text-xs font-bold text-stone-500">{statusLabel(row.status)}</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200">
              <div
                className="h-full rounded-full bg-teal-700 transition-[width]"
                style={{ width: `${Math.max(0, Math.min(row.progress, 100))}%` }}
              />
            </div>
            {row.error ? <p className="mt-2 text-xs font-semibold text-red-700">{row.error}</p> : null}
            {row.attachment ? (
              <p className="mt-2 truncate text-xs text-stone-500">{row.attachment.storage_key}</p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function newUploadRow(filename: string): UploadRow {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    filename,
    progress: 0,
    status: "queued",
    error: null,
    attachment: null,
  };
}

async function createUploadUrl(
  file: File,
  purpose: AttachmentUploadPurpose,
): Promise<UploadUrlResponse> {
  const response = await fetchApi("/storage/upload-urls", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      content_length: file.size,
      purpose,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(readDetail(payload) ?? "업로드 URL을 만들지 못했다.");
  }
  return parseUploadUrl(payload);
}

function putFileWithProgress(
  upload: UploadUrlResponse,
  file: File,
  onProgress: (progress: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", upload.upload_url);
    for (const [key, value] of Object.entries(upload.headers)) {
      request.setRequestHeader(key, value);
    }
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        resolve();
        return;
      }
      reject(new Error(`RustFS 업로드 실패 (${request.status})`));
    };
    request.onerror = () => reject(new Error("RustFS 업로드 네트워크 오류"));
    request.send(file);
  });
}

async function createAttachment(
  target: AttachmentTarget,
  payload: Record<string, unknown>,
): Promise<StoredAttachment> {
  const response = await fetchApi(attachmentPath(target), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(readDetail(body) ?? "첨부 파일 등록에 실패했다.");
  }
  return parseStoredAttachment(body);
}

function attachmentPath(target: AttachmentTarget): string {
  if (target.kind === "trip") {
    return `/trips/${encodeURIComponent(target.tripId)}/attachments`;
  }
  if (target.kind === "tripPoi") {
    return `/trips/${encodeURIComponent(target.tripId)}/pois/${encodeURIComponent(
      target.poiId,
    )}/attachments`;
  }
  if (target.kind === "noticePlan") {
    return `/admin/notice-plans/${encodeURIComponent(target.planId)}/attachments`;
  }
  return `/admin/notice-plans/${encodeURIComponent(target.planId)}/pois/${encodeURIComponent(
    target.poiId,
  )}/attachments`;
}

function statusLabel(status: UploadRow["status"]): string {
  switch (status) {
    case "queued":
      return "대기";
    case "presigning":
      return "URL 준비";
    case "uploading":
      return "업로드";
    case "finalizing":
      return "등록";
    case "done":
      return "완료";
    case "failed":
      return "실패";
  }
}

function parseUploadUrl(payload: unknown): UploadUrlResponse {
  const record = requireRecord(payload);
  return {
    bucket: requireString(record.bucket),
    storage_key: requireString(record.storage_key),
    upload_url: requireString(record.upload_url),
    headers: parseStringRecord(record.headers),
    public_url: optionalString(record.public_url),
  };
}

function parseStoredAttachment(payload: unknown): StoredAttachment {
  const record = requireRecord(payload);
  return {
    id: requireString(record.id),
    original_filename: requireString(record.original_filename),
    storage_key: requireString(record.storage_key),
    public_url: optionalString(record.public_url),
  };
}

function parseStringRecord(payload: unknown): Record<string, string> {
  const record = requireRecord(payload);
  return Object.fromEntries(
    Object.entries(record).map(([key, value]) => [key, requireString(value)]),
  );
}

function requireRecord(value: unknown): Record<string, unknown> {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new Error("API 응답 형식이 올바르지 않다.");
}

function requireString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  throw new Error("API 응답 문자열 형식이 올바르지 않다.");
}

function optionalString(value: unknown): string | null {
  if (value === null) {
    return null;
  }
  return requireString(value);
}

function readDetail(payload: unknown): string | null {
  if (
    payload !== null &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return null;
}
