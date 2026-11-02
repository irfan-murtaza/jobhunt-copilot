"use client";

import { useCallback, useEffect, useState } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { api, json } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { STAGES, type Application, type Board, type Stage } from "@/lib/types";
import { timeAgo, titleCase } from "@/lib/format";
import { Alert, Badge, Button, Card, PageHeader, ScorePill, Spinner, Textarea } from "@/components/ui";

export default function TrackerPage() {
  const user = useRequireAuth();
  const [board, setBoard] = useState<Board | null>(null);
  const [selected, setSelected] = useState<Application | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const load = useCallback(() => api<Board>("/applications").then(setBoard).catch((e) => setError(String(e))), []);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function move(id: string, stage: Stage) {
    if (!board) return;
    // Optimistic update, then reconcile with the server's answer.
    const current = Object.values(board.columns).flat().find((a) => a.id === id);
    if (!current || current.stage === stage) return;
    setBoard({
      ...board,
      columns: Object.fromEntries(STAGES.map((s) => [s, board.columns[s].filter((a) => a.id !== id).concat(s === stage ? [{ ...current, stage }] : [])])) as Board["columns"],
    });
    try {
      const updated = await api<Application>(`/applications/${id}`, { method: "PATCH", body: json({ stage }) });
      if (selected?.id === id) setSelected(updated);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      load();
    }
  }

  function onDragEnd(event: DragEndEvent) {
    const stage = event.over?.id as Stage | undefined;
    if (stage && STAGES.includes(stage)) move(String(event.active.id), stage);
  }

  if (!user) return null;
  return (
    <>
      <PageHeader
        title="Application tracker"
        description="Drag cards between stages. Moving to Applied schedules a follow-up reminder for seven days later."
        actions={board && board.reminders_due > 0 ? <Badge tone="amber">{board.reminders_due} follow-up{board.reminders_due > 1 ? "s" : ""} due</Badge> : undefined}
      />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {!board ? <Spinner /> : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="grid gap-3 md:grid-cols-5">
            {STAGES.map((stage) => (
              <Column key={stage} stage={stage} items={board.columns[stage]} onOpen={setSelected} selectedId={selected?.id} />
            ))}
          </div>
        </DndContext>
      )}
      {selected && <ApplicationDrawer application={selected} onClose={() => setSelected(null)} onChange={(a) => { setSelected(a); load(); }} onMove={(stage) => move(selected.id, stage)} />}
    </>
  );
}

function Column({ stage, items, onOpen, selectedId }: { stage: Stage; items: Application[]; onOpen: (a: Application) => void; selectedId?: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  return (
    <div ref={setNodeRef} className={`flex min-h-[60vh] flex-col rounded-lg border p-2 transition ${isOver ? "border-zinc-900 bg-zinc-100 dark:border-zinc-100 dark:bg-zinc-800" : "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50"}`}>
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="text-sm font-semibold">{titleCase(stage)}</h2>
        <span className="text-xs text-zinc-500">{items.length}</span>
      </div>
      <div className="space-y-2">
        {items.map((a) => <CardItem key={a.id} application={a} onOpen={onOpen} selected={a.id === selectedId} />)}
      </div>
    </div>
  );
}

function CardItem({ application, onOpen, selected }: { application: Application; onOpen: (a: Application) => void; selected: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: application.id });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(application)}
      className={`cursor-grab rounded-md border bg-white p-2 text-sm shadow-sm active:cursor-grabbing dark:bg-zinc-900 ${isDragging ? "opacity-70" : ""} ${selected ? "border-zinc-900 dark:border-zinc-100" : "border-zinc-200 dark:border-zinc-800"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium leading-tight">{application.job.title}</p>
        <ScorePill score={application.judge_score} />
      </div>
      <p className="mt-1 text-xs text-zinc-500">{application.job.company}</p>
      <div className="mt-2 flex flex-wrap gap-1 text-xs">
        {application.follow_up_due && <Badge tone="amber">follow up</Badge>}
        {application.resume_document_id && <Badge tone="blue">resume v</Badge>}
        <span className="text-zinc-400">{timeAgo(application.updated_at)}</span>
      </div>
    </div>
  );
}

function ApplicationDrawer({ application, onClose, onChange, onMove }: { application: Application; onClose: () => void; onChange: (a: Application) => void; onMove: (s: Stage) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function addNote() {
    if (!note.trim()) return;
    setBusy(true);
    try {
      onChange(await api<Application>(`/applications/${application.id}/notes`, { method: "POST", body: json({ body: note }) }));
      setNote("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try {
      onChange(await api<Application>(`/applications/${application.id}`, { method: "PATCH", body: json(body) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("Remove this job from your board?")) return;
    await api(`/applications/${application.id}`, { method: "DELETE" });
    onClose();
    onChange(application);
  }

  return (
    <div className="fixed inset-y-0 right-0 z-20 w-full max-w-md overflow-y-auto border-l border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{application.job.title}</h2>
          <p className="text-sm text-zinc-500">{application.job.company}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <a href={application.job.url} target="_blank" rel="noreferrer noopener"><Button variant="secondary" size="sm">Open listing</Button></a>
        <Button variant="danger" size="sm" onClick={remove}>Remove</Button>
      </div>

      <Card className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase text-zinc-500">Stage</p>
        <div className="flex flex-wrap gap-1">
          {STAGES.map((s) => (
            <Button key={s} size="sm" variant={s === application.stage ? "primary" : "secondary"} onClick={() => onMove(s)}>{titleCase(s)}</Button>
          ))}
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-zinc-500">Applied</dt><dd>{application.applied_at ? new Date(application.applied_at).toLocaleDateString() : "–"}</dd>
          <dt className="text-zinc-500">Follow up</dt>
          <dd className="flex items-center gap-2">
            <input type="date" className="rounded border border-zinc-300 px-1 text-sm dark:border-zinc-700 dark:bg-zinc-900" value={application.follow_up_at ? application.follow_up_at.slice(0, 10) : ""} onChange={(e) => patch(e.target.value ? { follow_up_at: new Date(e.target.value).toISOString() } : { clear_follow_up: true })} />
            {application.follow_up_due && <Badge tone="amber">due</Badge>}
          </dd>
        </dl>
      </Card>

      <Card className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase text-zinc-500">Add a note</p>
        <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Recruiter call on Tuesday…" />
        <div className="mt-2 flex justify-end"><Button size="sm" onClick={addNote} disabled={busy || !note.trim()}>Add note</Button></div>
      </Card>

      {error && <div className="mt-4"><Alert>{error}</Alert></div>}

      <div className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase text-zinc-500">History</p>
        <ol className="space-y-2 border-l border-zinc-200 pl-3 text-sm dark:border-zinc-800">
          {[...application.events].reverse().map((e) => (
            <li key={e.id}>
              <p className={e.kind === "note" ? "" : "text-zinc-500"}>{e.body}</p>
              <p className="text-xs text-zinc-400">{new Date(e.created_at).toLocaleString()}{e.source !== "user" ? ` · ${e.source}` : ""}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
