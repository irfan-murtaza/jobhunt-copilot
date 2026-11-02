"use client";

import { useCallback, useEffect, useState } from "react";
import { api, json } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { Match, MatchDetail, MatchList, ScoreSummary } from "@/lib/types";
import { describeLocation, pct, timeAgo, titleCase } from "@/lib/format";
import { Alert, Badge, Button, Card, Empty, PageHeader, ScorePill, Spinner } from "@/components/ui";

export default function MatchesPage() {
  const user = useRequireAuth();
  const [matches, setMatches] = useState<MatchList | null>(null);
  const [includeFiltered, setIncludeFiltered] = useState(false);
  const [selected, setSelected] = useState<MatchDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: "50" });
    if (includeFiltered) params.set("include_filtered", "true");
    api<MatchList>(`/matches?${params}`).then(setMatches).catch((e) => setError(String(e)));
  }, [includeFiltered]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function scoreNow() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const s = await api<ScoreSummary>("/matches/score/sync?judge_pool=10", { method: "POST" });
      setNotice(`Considered ${s.considered} new jobs: ${s.filtered_out} filtered out, ${s.scored} scored, ${s.judged} judged (judge cost $${s.judge_cost_usd.toFixed(4)}).`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function open(match: Match) {
    setSelected(await api<MatchDetail>(`/matches/${match.job.id}`));
  }

  async function judge(match: Match) {
    setBusy(true);
    try {
      setSelected(await api<MatchDetail>(`/matches/${match.job.id}/judge`, { method: "POST" }));
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save(match: Match) {
    try {
      await api("/applications", { method: "POST", body: json({ job_id: match.job.id }) });
      setNotice(`Saved "${match.job.title}" to your tracker.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!user) return null;
  return (
    <>
      <PageHeader
        title="Your matches"
        description="Ranked by the judge's fit score, then by hybrid score. Click a job to see exactly why it ranked where it did."
        actions={<>
          <label className="flex items-center gap-2 text-sm text-zinc-600"><input type="checkbox" checked={includeFiltered} onChange={(e) => setIncludeFiltered(e.target.checked)} /> Show filtered-out</label>
          <Button onClick={scoreNow} disabled={busy}>{busy ? "Scoring…" : "Score new jobs"}</Button>
        </>}
      />
      {notice && <div className="mb-4"><Alert tone="green">{notice}</Alert></div>}
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      <div className="grid gap-6 lg:grid-cols-[1fr_460px]">
        <div>
          {!matches ? <Spinner /> : matches.items.length === 0 ? (
            <Empty title="Nothing scored yet">Upload a profile, fetch jobs, then click “Score new jobs”. The daily agent does this automatically once it is running.</Empty>
          ) : (
            <ul className="space-y-2">
              {matches.items.map((m) => (
                <li key={m.job.id}>
                  <button onClick={() => open(m)} className={`w-full rounded-lg border bg-white p-3 text-left transition hover:border-zinc-400 dark:bg-zinc-900 dark:hover:border-zinc-600 ${selected?.job.id === m.job.id ? "border-zinc-900 dark:border-zinc-100" : "border-zinc-200 dark:border-zinc-800"} ${m.passed_filters ? "" : "opacity-60"}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{m.job.title}</p>
                        <p className="text-sm text-zinc-500">{m.job.company} · {timeAgo(m.job.posted_at ?? m.job.fetched_at)}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {m.passed_filters ? <ScorePill score={m.judge_score} /> : <Badge tone="red">filtered</Badge>}
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                      {m.passed_filters ? (
                        <>
                          <span title="Mean cosine similarity of the top-3 retrieved evidence items">similarity {pct(m.similarity_score)}</span>
                          <span>·</span>
                          <span title="Share of must-have skills found in your profile">skills {pct(m.skill_coverage)}</span>
                          <span>·</span>
                          <span title="50/50 blend of similarity and skill coverage">hybrid {pct(m.hybrid_score)}</span>
                          {m.judgement && <><span>·</span><span className="truncate text-zinc-700 dark:text-zinc-300">{m.judgement.verdict}</span></>}
                        </>
                      ) : (
                        <span className="text-red-700 dark:text-red-300">{m.filter_reasons.filter((r) => !r.startsWith("note:")).join("; ")}</span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <aside>
          {selected ? <ReasoningPanel match={selected} onJudge={() => judge(selected)} onSave={() => save(selected)} busy={busy} /> : (
            <Card><p className="text-sm text-zinc-500">Select a match to see the reasoning: which filters it passed, which of your bullets were retrieved, which must-have skills matched, and the judge&apos;s cited strengths and gaps.</p></Card>
          )}
        </aside>
      </div>
    </>
  );
}

function ReasoningPanel({ match, onJudge, onSave, busy }: { match: MatchDetail; onJudge: () => void; onSave: () => void; busy: boolean }) {
  const j = match.judgement;
  const ex = match.job.extraction;
  const notes = match.filter_reasons.filter((r) => r.startsWith("note:")).map((r) => r.slice(5).trim());
  const reasons = match.filter_reasons.filter((r) => !r.startsWith("note:"));
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="font-semibold">{match.job.title}</h2>
            <p className="text-sm text-zinc-500">{match.job.company}</p>
          </div>
          <ScorePill score={match.judge_score} />
        </div>
        {ex && <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{ex.summary}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={match.job.url} target="_blank" rel="noreferrer noopener"><Button variant="secondary" size="sm">Open listing</Button></a>
          <Button size="sm" onClick={onSave}>Save to tracker</Button>
          {match.passed_filters && <Button variant="secondary" size="sm" onClick={onJudge} disabled={busy}>{j ? "Re-judge" : "Judge now"}</Button>}
        </div>
      </Card>

      <Card>
        <h3 className="mb-2 text-sm font-semibold">1. Hard filters {match.passed_filters ? <Badge tone="green">passed</Badge> : <Badge tone="red">excluded</Badge>}</h3>
        {ex && <p className="text-sm text-zinc-600 dark:text-zinc-400">Eligibility: {describeLocation(ex.location)} · {titleCase(ex.remote)} · {titleCase(ex.seniority)}</p>}
        {reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-red-700 dark:text-red-300">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
        {notes.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-amber-700 dark:text-amber-300">{notes.map((r) => <li key={r}>{r}</li>)}</ul>}
      </Card>

      {match.passed_filters && (
        <Card>
          <h3 className="mb-2 text-sm font-semibold">2. Hybrid score {pct(match.hybrid_score)}</h3>
          {match.skills && (
            <div className="mb-3 text-sm">
              <p className="text-zinc-500">Must-have skills: {pct(match.skills.ratio)} covered</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {match.skills.matched.map((s) => <Badge key={s} tone="green">{s}</Badge>)}
                {match.skills.missing.map((s) => <Badge key={s} tone="red">{s}</Badge>)}
              </div>
            </div>
          )}
          <p className="text-sm text-zinc-500">Retrieved evidence (similarity {pct(match.similarity_score)}):</p>
          <ul className="mt-1 space-y-1">
            {match.matched_evidence.slice(0, 5).map((e) => (
              <li key={e.evidence_id} className="rounded bg-zinc-50 p-2 text-xs dark:bg-zinc-800">
                <span className="mr-2 font-mono text-zinc-400">{pct(e.similarity)}</span>{e.text}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {j && (
        <Card>
          <h3 className="mb-2 text-sm font-semibold">3. Judge <Badge tone={j.recommendation === "apply" ? "green" : j.recommendation === "maybe" ? "amber" : "red"}>{j.recommendation}</Badge></h3>
          <p className="text-sm">{j.verdict}</p>
          {j.strengths.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium uppercase text-zinc-500">Strengths, citing your resume</p>
              <ul className="mt-1 space-y-2">
                {j.strengths.map((s, i) => (
                  <li key={i} className="border-l-2 border-emerald-400 pl-2 text-sm">
                    <p className="text-zinc-500">{s.requirement}</p>
                    <p className="italic">“{s.quote}”</p>
                    {s.path && <p className="font-mono text-xs text-zinc-400">{s.path}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {j.gaps.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium uppercase text-zinc-500">Gaps</p>
              <ul className="mt-1 list-disc pl-5 text-sm">{j.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
            </div>
          )}
          {j.risks.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium uppercase text-zinc-500">Risks</p>
              <ul className="mt-1 list-disc pl-5 text-sm text-amber-700 dark:text-amber-300">{j.risks.map((g) => <li key={g}>{g}</li>)}</ul>
            </div>
          )}
          <p className="mt-3 text-xs text-zinc-400">
            {j.model} · {j.cost_usd != null ? `$${j.cost_usd.toFixed(4)}` : "cost n/a"} · {j.latency_ms} ms{j.dropped_citations > 0 ? ` · ${j.dropped_citations} unverifiable citation(s) dropped` : ""}
          </p>
        </Card>
      )}
    </div>
  );
}
