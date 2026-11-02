"use client";

import { useEffect, useState } from "react";
import { api, json } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Preferences } from "@/lib/types";
import { Alert, Button, Card, Field, Input, PageHeader, Spinner } from "@/components/ui";

const SENIORITY = ["intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager", "director"];
const splitList = (value: string) => value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);

export default function PreferencesPage() {
  const user = useRequireAuth();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) api<Preferences>("/preferences").then(setPrefs).catch((e) => setError(String(e)));
  }, [user]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!prefs) return;
    setBusy(true);
    setError(null);
    try {
      setPrefs(await api<Preferences>("/preferences", { method: "PUT", body: json(prefs) }));
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;
  if (!prefs) return error ? <Alert>{error}</Alert> : <Spinner />;
  const set = (patch: Partial<Preferences>) => {
    setPrefs({ ...prefs, ...patch });
    setSaved(false);
  };

  return (
    <>
      <PageHeader title="Preferences" description="Hard filters applied before any job is scored, and how many jobs the judge looks at each run." />
      <form onSubmit={save} className="space-y-6">
        <Card>
          <h2 className="mb-4 font-semibold">Where you are</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Country" hint="ISO alpha-2, e.g. PK"><Input maxLength={2} value={prefs.country ?? ""} onChange={(e) => set({ country: e.target.value.toUpperCase() || null })} /></Field>
            <Field label="Timezone" hint="IANA, e.g. Asia/Karachi"><Input value={prefs.timezone ?? ""} onChange={(e) => set({ timezone: e.target.value || null })} /></Field>
          </div>
        </Card>
        <Card>
          <h2 className="mb-4 font-semibold">What you want</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Minimum salary" hint="USD per year; jobs stating less are hidden">
              <Input type="number" min={0} value={prefs.min_salary_usd ?? ""} onChange={(e) => set({ min_salary_usd: e.target.value ? Number(e.target.value) : null })} />
            </Field>
            <Field label="Seniority levels" hint="leave all unchecked to accept any">
              <div className="flex flex-wrap gap-2 pt-1">
                {SENIORITY.map((level) => (
                  <label key={level} className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={prefs.seniority_levels.includes(level)} onChange={(e) => set({ seniority_levels: e.target.checked ? [...prefs.seniority_levels, level] : prefs.seniority_levels.filter((l) => l !== level) })} />
                    {level}
                  </label>
                ))}
              </div>
            </Field>
            <Field label="Excluded keywords" hint="comma separated; title or description"><Input defaultValue={prefs.excluded_keywords.join(", ")} onBlur={(e) => set({ excluded_keywords: splitList(e.target.value) })} /></Field>
            <Field label="Required keywords" hint="all must appear"><Input defaultValue={prefs.required_keywords.join(", ")} onBlur={(e) => set({ required_keywords: splitList(e.target.value) })} /></Field>
          </div>
        </Card>
        <Card>
          <h2 className="mb-4 font-semibold">Daily run</h2>
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Judge pool" hint="top N by hybrid score sent to the LLM judge"><Input type="number" min={1} max={200} value={prefs.judge_pool_size} onChange={(e) => set({ judge_pool_size: Number(e.target.value) })} /></Field>
            <Field label="Shortlist size" hint="jobs in the daily digest"><Input type="number" min={1} max={50} value={prefs.shortlist_size} onChange={(e) => set({ shortlist_size: Number(e.target.value) })} /></Field>
            <Field label="Email digest">
              <label className="flex items-center gap-2 pt-2 text-sm"><input type="checkbox" checked={prefs.digest_email_enabled} onChange={(e) => set({ digest_email_enabled: e.target.checked })} /> Send the daily digest by email</label>
            </Field>
          </div>
        </Card>
        {error && <Alert>{error}</Alert>}
        {saved && <Alert tone="green">Preferences saved. Existing scores keep their filter results until the next scoring run.</Alert>}
        <div className="flex justify-end"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</Button></div>
      </form>
    </>
  );
}
