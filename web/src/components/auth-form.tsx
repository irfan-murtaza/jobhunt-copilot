"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Alert, Button, Card, Field, Input } from "@/components/ui";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name);
      router.replace(mode === "register" ? "/profile" : "/matches");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-10 max-w-sm">
      <Card>
        <h1 className="mb-4 text-xl font-semibold">{mode === "login" ? "Log in" : "Create your account"}</h1>
        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && (
            <Field label="Name" hint="optional">
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </Field>
          <Field label="Password" hint={mode === "register" ? "10+ characters" : undefined}>
            <Input type="password" required minLength={mode === "register" ? 10 : 1} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "…" : mode === "login" ? "Log in" : "Create account"}</Button>
        </form>
        <p className="mt-4 text-center text-sm text-zinc-500">
          {mode === "login" ? (
            <>No account? <Link className="underline" href="/register">Register</Link></>
          ) : (
            <>Already registered? <Link className="underline" href="/login">Log in</Link></>
          )}
        </p>
      </Card>
    </div>
  );
}
