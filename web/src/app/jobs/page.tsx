"use client";

import { useCallback, useEffect, useState } from "react";
import { api, json } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Job, JobDetail, JobList, SourceStatus } from "@/lib/types";
import { describeLocation, timeAgo, titleCase } from "@/lib/format";
import { Alert, Badge, Button, Card, Empty, Field, Input, PageHeader, Select, Spinner, Textarea } from "@/components/ui";

const SOURCES = ["remotive", "remoteok", "weworkremotely", "hackernews", "greenhouse", "lever", "manual"];

export default function JobsPage() {
  const user = useRequireAuth();
  const [jobs, setJobs] = useState<JobList | null>(null);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [extractedOnly, setExtractedOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<JobDetail | null>(null);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: "25", offset: String(offset) });
    if (q) params.set("q", q);
    if (source) params.set("source", source);
    if (extractedOnly) params.set("extracted_only", "true");
    api<JobList>(`/jobs?${params}`).then(setJobs).catch((e) => setError(String(e)));
  }, [q, source, extractedOnly, offset]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);
  useEffect(() => {
    if (user) api<SourceStatus[]>("/jobs/sources").then(setSources).catch(() => undefined);
  }, [user]);

  async function ingest() {
    try {
      const res = await api<{ detail: string }>("/jobs/ingest", { method: "POST" });
      setNotice(`${res.detail}. Refresh in a minute.`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function save(job: Job) {
    try {
      await api("/applications", { method: "POST", body: json({ job_id: job.id }) });
      setNotice(`Saved "${job.title}" to your tracker.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!user) return null;
  return (
    <>
      <PageHeader
        title="Job feed"
        description="Every remote posting ingested from public boards, deduplicated across sources."
        actions={<>
          <Button variant="secondary" onClick={() => setShowManual((s) => !s)}>Add manually</Button>
          <Button onClick={ingest}>Fetch new jobs</Button>
        </>}
      />
      {notice && <div className="mb-4"><Alert tone="green">{notice}</Alert></div>}
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {showManual && <ManualJobForm onCreated={(job) => { setShowManual(false); setSelected(job); load(); }} />}

      <div className="mb-4 grid gap-3 md:grid-cols-[1fr_200px_auto]">
        <Input placeholder="Search title or company" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
        <Select value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
          <option value="">All sources</option>
          {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={extractedOnly} onChange={(e) => setExtractedOnly(e.target.checked)} /> Extracted only</label>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div>
          {!jobs ? <Spinner /> : jobs.items.length === 0 ? (
            <Empty title="No jobs yet">Click “Fetch new jobs” to pull from the public boards, or add one manually.</Empty>
          ) : (
            <ul className="space-y-2">
              {jobs.items.map((job) => (
                <li key={job.id}>
                  <button onClick={() => api<JobDetail>(`/jobs/${job.id}`).then(setSelected)} className={`w-full rounded-lg border p-3 text-left transition hover:border-zinc-400 dark:hover:border-zinc-600 ${selected?.id === job.id ? "border-zinc-900 dark:border-zinc-100" : "border-zinc-200 dark:border-zinc-800"} bg-white dark:bg-zinc-900`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">{job.title}</p>
                        <p className="text-sm text-zinc-500">{job.company}{job.location_text ? ` · ${job.location_text}` : ""}</p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-zinc-500">
                        <span>{timeAgo(job.posted_at ?? job.fetched_at)}</span>
                        <Badge>{job.source}</Badge>
                      </div>
                    </div>
                    {job.extraction && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        <Badge tone="blue">{describeLocation(job.extraction.location)}</Badge>
                        <Badge>{titleCase(job.extraction.seniority)}</Badge>
                        {job.extraction.must_have_skills.slice(0, 5).map((s) => <Badge key={s}>{s}</Badge>)}
                      </div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {jobs && jobs.total > jobs.limit && (
            <div className="mt-4 flex items-center justify-between text-sm text-zinc-500">
              <span>{offset + 1}–{Math.min(offset + jobs.limit, jobs.total)} of {jobs.total}</span>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</Button>
                <Button variant="secondary" size="sm" disabled={offset + jobs.limit >= jobs.total} onClick={() => setOffset(offset + 25)}>Next</Button>
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          {selected ? <JobPanel job={selected} onSave={() => save(selected)} /> : (
            <Card>
              <h2 className="mb-3 font-semibold">Sources</h2>
              <ul className="space-y-2 text-sm">
                {sources.map((s) => (
                  <li key={s.name} className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium">{s.name}</p>
                      <p className="text-xs text-zinc-500">{s.last_fetched_at ? `${timeAgo(s.last_fetched_at)} · ${s.last_items_seen} seen, ${s.last_items_new} new` : "never fetched"}</p>
                      {s.last_error && <p className="text-xs text-red-600">{s.last_error}</p>}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-zinc-400">{sources.map((s) => s.attribution).join(" ")}</p>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}

export function JobPanel({ job, onSave }: { job: JobDetail; onSave?: () => void }) {
  const ex = job.extraction;
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{job.title}</h2>
          <p className="text-sm text-zinc-500">{job.company}</p>
        </div>
        <Badge>{job.source}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <a href={job.url} target="_blank" rel="noreferrer noopener"><Button variant="secondary" size="sm">Open listing</Button></a>
        {onSave && <Button size="sm" onClick={onSave}>Save to tracker</Button>}
      </div>
      {ex ? (
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-zinc-500">Eligibility</dt><dd>{describeLocation(ex.location)}{ex.location.excluded_countries.length ? ` (not ${ex.location.excluded_countries.join(", ")})` : ""}</dd>
          <dt className="text-zinc-500">Remote</dt><dd>{titleCase(ex.remote)}</dd>
          <dt className="text-zinc-500">Seniority</dt><dd>{titleCase(ex.seniority)}{ex.years_experience_min ? ` · ${ex.years_experience_min}+ yrs` : ""}</dd>
          <dt className="text-zinc-500">Type</dt><dd>{titleCase(ex.employment_type)}</dd>
          <dt className="text-zinc-500">Salary</dt><dd>{ex.salary?.text ?? job.salary_text ?? "Not stated"}</dd>
          <dt className="text-zinc-500">Visa</dt><dd>{titleCase(ex.visa_sponsorship)}</dd>
          <dt className="text-zinc-500">Must have</dt><dd className="flex flex-wrap gap-1">{ex.must_have_skills.map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</dd>
          <dt className="text-zinc-500">Nice to have</dt><dd className="flex flex-wrap gap-1">{ex.nice_to_have_skills.map((s) => <Badge key={s}>{s}</Badge>)}</dd>
          <dt className="text-zinc-500">Confidence</dt><dd>{ex.confidence}</dd>
        </dl>
      ) : (
        <p className="mt-4 text-sm text-zinc-500">Extraction {job.extraction_status}. Requirements appear once the worker has processed this job.</p>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium">Full description</summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-sans text-sm text-zinc-700 dark:text-zinc-300">{job.description}</pre>
      </details>
      {job.extraction_cost_usd != null && <p className="mt-3 text-xs text-zinc-400">Extracted by {job.extraction_model} · ${job.extraction_cost_usd.toFixed(4)} · {job.extraction_latency_ms} ms</p>}
    </Card>
  );
}

function ManualJobForm({ onCreated }: { onCreated: (job: JobDetail) => void }) {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card className="mb-6">
      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            onCreated(await api<JobDetail>("/jobs/manual", { method: "POST", body: json({ url: url || null, description: description || null }) }));
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Job URL" hint="public page; fetched and extracted"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></Field>
        <Field label="Or paste the description"><Textarea rows={5} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        {error && <Alert>{error}</Alert>}
        <Button type="submit" disabled={busy || (!url && !description)}>{busy ? "Extracting…" : "Add job"}</Button>
      </form>
    </Card>
  );
}
