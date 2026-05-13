import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const adminPagePath = resolve(__dirname, "../app/admin/page.tsx");

test("admin UI exposes priority datasets for feature, POI, raw, and ETL state", async () => {
  const source = await readFile(adminPagePath, "utf8");

  for (const expected of [
    "Feature DB",
    "POI DB",
    "Beach Raw",
    "Beach Domain",
    "Dagster ETL",
    "Ops Raw",
    "features",
    "trip_pois",
    "beach_source_records",
    "beach_index_forecasts",
    "etl_run_logs",
    "api_call_log",
    "email_queue",
    "admin_audit_log",
  ]) {
    assert.match(source, new RegExp(JSON.stringify(expected).slice(1, -1)));
  }
});

test("admin UI gives Dagster status a first-screen affordance", async () => {
  const source = await readFile(adminPagePath, "utf8");

  assert.match(source, /priority datasets/);
  assert.match(source, /Dagster status/);
  assert.match(source, /getDagsterAdminUrl/);
  assert.match(source, /selectDataset\(dataset\.table_name\)/);
});

test("signup and login UI expose consent and OAuth entry points", async () => {
  const signupSource = await readFile(resolve(__dirname, "../app/signup/page.tsx"), "utf8");
  const loginSource = await readFile(resolve(__dirname, "../app/login/page.tsx"), "utf8");

  for (const expected of [
    "tosAgreed",
    "privacyAgreed",
    "demographicUseAgreed",
    "locationUseAgreed",
    "marketingAgreed",
    "consent_version",
  ]) {
    assert.match(signupSource, new RegExp(expected));
  }

  assert.match(loginSource, /oauthProviders/);
  assert.match(loginSource, /auth\/oauth\/\$\{provider\.provider\}\/start/);
});
