"use client";

import { useEffect, useState } from "react";
import { api, ApiError, json } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type { ProfileDocument, ProfileRead } from "@/lib/types";
import { Alert, Badge, Button, Card, Empty, Field, Input, PageHeader, Spinner } from "@/components/ui";
import { ProfileEditor } from "@/components/profile-editor";

const emptyDocument = (): ProfileDocument => ({
  name: null, headline: null, location: null, country_code: null, email: null, phone: null, links: [], summary: null,
  roles: [], projects: [], skills: [], education: [], certifications: [], languages: [],
});

export default function ProfilePage() {
  const user = useRequireAuth();
  const [profile, setProfile] = useState<ProfileRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    api<ProfileRead>("/profile")
      .then(setProfile)
      .catch((e: unknown) => {
        if (!(e instanceof ApiError && e.status === 404)) setError(String(e));
      })
      .finally(() => setLoading(false));
  }, [user]);

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!(form.get("resume") as File)?.size) return;
    if (!(form.get("linkedin") as File)?.size) form.delete("linkedin");
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<ProfileRead>("/profile/upload", { method: "POST", body: form });
      setProfile(result);
      setNotice(`Parsed ${result.document.roles.length} roles and ${result.evidence_count} evidence items. Review and edit below.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function save(document: ProfileDocument) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api<ProfileRead>("/profile", { method: "PUT", body: json(document) });
      setProfile(result);
      setNotice(`Saved version ${result.version}. ${result.evidence_count} evidence items re-embedded; matches will re-score on the next run.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;
  return (
    <>
      <PageHeader
        title="Your profile"
        description="Parsed from your resume, then edited by you. The edited version is the single source of truth for scoring and tailoring."
        actions={profile && <Badge>version {profile.version}</Badge>}
      />
      <Card className="mb-6">
        <form onSubmit={upload} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <Field label="Resume" hint="PDF or DOCX, 5 MB max">
            <Input type="file" name="resume" accept=".pdf,.docx" required />
          </Field>
          <Field label="LinkedIn PDF export" hint="optional">
            <Input type="file" name="linkedin" accept=".pdf" />
          </Field>
          <Button type="submit" disabled={busy}>{busy ? "Parsing…" : profile ? "Re-parse and replace" : "Upload and parse"}</Button>
        </form>
        {profile?.source_filename && <p className="mt-2 text-xs text-zinc-500">Last upload: {profile.source_filename}</p>}
      </Card>
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="green">{notice}</Alert></div>}
      {loading ? (
        <Spinner />
      ) : profile ? (
        <ProfileEditor key={profile.version} initial={profile.document} onSave={save} busy={busy} />
      ) : (
        <Empty title="No profile yet">
          <p>Upload your resume above. Parsing uses the extraction model and takes a few seconds.</p>
          <p className="mt-3">
            <Button variant="secondary" size="sm" onClick={() => save(emptyDocument())} disabled={busy}>Or start from a blank profile</Button>
          </p>
        </Empty>
      )}
    </>
  );
}
