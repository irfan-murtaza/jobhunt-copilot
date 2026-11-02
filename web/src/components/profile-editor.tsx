"use client";

import { useState } from "react";
import type { Education, ProfileDocument, Project, Role } from "@/lib/types";
import { Button, Card, Field, Input, Textarea } from "@/components/ui";

type Props = { initial: ProfileDocument; onSave: (doc: ProfileDocument) => Promise<void>; busy: boolean };

const emptyRole = (): Role => ({ title: "", company: "", location: null, start: null, end: null, bullets: [] });
const emptyProject = (): Project => ({ name: "", description: "", url: null, technologies: [], bullets: [] });
const emptyEducation = (): Education => ({ institution: "", degree: null, field: null, start: null, end: null });

const splitList = (value: string) => value.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
const splitLines = (value: string) => value.split("\n").map((s) => s.trim()).filter(Boolean);
const orNull = (value: string) => (value.trim() ? value.trim() : null);

export function ProfileEditor({ initial, onSave, busy }: Props) {
  const [doc, setDoc] = useState<ProfileDocument>(initial);
  const [dirty, setDirty] = useState(false);

  function update(patch: Partial<ProfileDocument>) {
    setDoc((d) => ({ ...d, ...patch }));
    setDirty(true);
  }
  function updateRole(i: number, patch: Partial<Role>) {
    update({ roles: doc.roles.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) });
  }
  function updateProject(i: number, patch: Partial<Project>) {
    update({ projects: doc.projects.map((p, idx) => (idx === i ? { ...p, ...patch } : p)) });
  }
  function updateEducation(i: number, patch: Partial<Education>) {
    update({ education: doc.education.map((e, idx) => (idx === i ? { ...e, ...patch } : e)) });
  }

  return (
    <form
      className="space-y-6"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSave(doc);
        setDirty(false);
      }}
    >
      <Card>
        <h2 className="mb-4 font-semibold">Basics</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Name"><Input value={doc.name ?? ""} onChange={(e) => update({ name: orNull(e.target.value) })} /></Field>
          <Field label="Headline"><Input value={doc.headline ?? ""} onChange={(e) => update({ headline: orNull(e.target.value) })} /></Field>
          <Field label="Location"><Input value={doc.location ?? ""} onChange={(e) => update({ location: orNull(e.target.value) })} /></Field>
          <Field label="Country code" hint="ISO alpha-2, drives eligibility checks"><Input maxLength={2} value={doc.country_code ?? ""} onChange={(e) => update({ country_code: orNull(e.target.value.toUpperCase()) })} /></Field>
        </div>
        <div className="mt-4">
          <Field label="Summary"><Textarea rows={3} value={doc.summary ?? ""} onChange={(e) => update({ summary: orNull(e.target.value) })} /></Field>
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">Experience</h2>
          <Button type="button" variant="secondary" size="sm" onClick={() => update({ roles: [...doc.roles, emptyRole()] })}>Add role</Button>
        </div>
        <div className="space-y-6">
          {doc.roles.map((role, i) => (
            <div key={i} className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
              <div className="grid gap-3 md:grid-cols-4">
                <Field label="Title"><Input value={role.title} onChange={(e) => updateRole(i, { title: e.target.value })} /></Field>
                <Field label="Company"><Input value={role.company} onChange={(e) => updateRole(i, { company: e.target.value })} /></Field>
                <Field label="Start" hint="YYYY-MM"><Input value={role.start ?? ""} onChange={(e) => updateRole(i, { start: orNull(e.target.value) })} /></Field>
                <Field label="End" hint="blank = present"><Input value={role.end ?? ""} onChange={(e) => updateRole(i, { end: orNull(e.target.value) })} /></Field>
              </div>
              <div className="mt-3">
                <Field label="Bullets" hint="one achievement per line; these become citable evidence">
                  <Textarea rows={Math.max(3, role.bullets.length + 1)} value={role.bullets.join("\n")} onChange={(e) => updateRole(i, { bullets: e.target.value.split("\n") })} onBlur={(e) => updateRole(i, { bullets: splitLines(e.target.value) })} />
                </Field>
              </div>
              <div className="mt-3 text-right">
                <Button type="button" variant="danger" size="sm" onClick={() => update({ roles: doc.roles.filter((_, idx) => idx !== i) })}>Remove role</Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">Projects</h2>
          <Button type="button" variant="secondary" size="sm" onClick={() => update({ projects: [...doc.projects, emptyProject()] })}>Add project</Button>
        </div>
        <div className="space-y-4">
          {doc.projects.map((project, i) => (
            <div key={i} className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
              <div className="grid gap-3 md:grid-cols-3">
                <Field label="Name"><Input value={project.name} onChange={(e) => updateProject(i, { name: e.target.value })} /></Field>
                <Field label="URL"><Input value={project.url ?? ""} onChange={(e) => updateProject(i, { url: orNull(e.target.value) })} /></Field>
                <Field label="Technologies" hint="comma separated"><Input value={project.technologies.join(", ")} onChange={(e) => updateProject(i, { technologies: splitList(e.target.value) })} /></Field>
              </div>
              <div className="mt-3">
                <Field label="Description"><Textarea rows={2} value={project.description} onChange={(e) => updateProject(i, { description: e.target.value })} /></Field>
              </div>
              <div className="mt-3 text-right">
                <Button type="button" variant="danger" size="sm" onClick={() => update({ projects: doc.projects.filter((_, idx) => idx !== i) })}>Remove</Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-4 font-semibold">Skills and education</h2>
        <Field label="Skills" hint="comma or newline separated">
          <Textarea rows={3} value={doc.skills.join(", ")} onChange={(e) => update({ skills: [e.target.value] })} onBlur={(e) => update({ skills: splitList(e.target.value) })} />
        </Field>
        <div className="mt-4 flex items-center justify-between">
          <h3 className="text-sm font-medium">Education</h3>
          <Button type="button" variant="secondary" size="sm" onClick={() => update({ education: [...doc.education, emptyEducation()] })}>Add</Button>
        </div>
        <div className="mt-2 space-y-3">
          {doc.education.map((ed, i) => (
            <div key={i} className="grid gap-3 md:grid-cols-5">
              <Input placeholder="Institution" value={ed.institution} onChange={(e) => updateEducation(i, { institution: e.target.value })} />
              <Input placeholder="Degree" value={ed.degree ?? ""} onChange={(e) => updateEducation(i, { degree: orNull(e.target.value) })} />
              <Input placeholder="Start" value={ed.start ?? ""} onChange={(e) => updateEducation(i, { start: orNull(e.target.value) })} />
              <Input placeholder="End" value={ed.end ?? ""} onChange={(e) => updateEducation(i, { end: orNull(e.target.value) })} />
              <Button type="button" variant="danger" size="sm" onClick={() => update({ education: doc.education.filter((_, idx) => idx !== i) })}>Remove</Button>
            </div>
          ))}
        </div>
      </Card>

      <div className="sticky bottom-4 flex justify-end">
        <Button type="submit" disabled={busy || !dirty}>{busy ? "Saving…" : dirty ? "Save profile" : "Saved"}</Button>
      </div>
    </form>
  );
}
