"use client";

import { useMemo, useState } from "react";
import { FileUploadPanel, type AttachmentTarget } from "./file-upload-panel";

export function UserAttachmentWorkbench() {
  const [targetMode, setTargetMode] = useState<"trip" | "tripPoi">("trip");
  const [tripId, setTripId] = useState("");
  const [poiId, setPoiId] = useState("");

  const target = useMemo<AttachmentTarget | null>(() => {
    const normalizedTripId = tripId.trim();
    const normalizedPoiId = poiId.trim();
    if (!normalizedTripId) {
      return null;
    }
    if (targetMode === "tripPoi") {
      return normalizedPoiId
        ? { kind: "tripPoi", tripId: normalizedTripId, poiId: normalizedPoiId }
        : null;
    }
    return { kind: "trip", tripId: normalizedTripId };
  }, [poiId, targetMode, tripId]);

  return (
    <section className="workspace" id="attachments" aria-label="여행 파일 첨부">
      <div>
        <p className="sectionLabel">Attachments</p>
        <h2>plan과 POI에 파일을 붙여 여행 자료를 함께 보관합니다.</h2>
      </div>
      <div className="grid gap-4">
        <div className="rounded-md border border-stone-300 bg-white p-4">
          <div className="flex flex-wrap gap-2">
            <button
              className={targetMode === "trip" ? "admin-top-button border-teal-700" : "admin-top-button"}
              type="button"
              onClick={() => setTargetMode("trip")}
            >
              plan
            </button>
            <button
              className={targetMode === "tripPoi" ? "admin-top-button border-teal-700" : "admin-top-button"}
              type="button"
              onClick={() => setTargetMode("tripPoi")}
            >
              POI
            </button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <label className="grid gap-2 text-sm font-bold text-stone-700">
              Trip ID
              <input
                className="admin-input font-mono"
                value={tripId}
                onChange={(event) => setTripId(event.target.value)}
              />
            </label>
            {targetMode === "tripPoi" ? (
              <label className="grid gap-2 text-sm font-bold text-stone-700">
                POI ID
                <input
                  className="admin-input font-mono"
                  value={poiId}
                  onChange={(event) => setPoiId(event.target.value)}
                />
              </label>
            ) : null}
          </div>
        </div>
        <FileUploadPanel
          title="여행 파일 업로드"
          target={target}
          purpose={targetMode === "tripPoi" ? "poi_attachment" : "plan_attachment"}
        />
      </div>
    </section>
  );
}
