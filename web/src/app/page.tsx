"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && user) router.replace("/matches");
  }, [loading, user, router]);
  if (loading || user) return null;
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-16">
      <p className="text-sm font-medium uppercase tracking-wide text-zinc-500">JobHunt Copilot</p>
      <h1 className="text-4xl font-semibold tracking-tight">Find remote jobs you are actually a fit for.</h1>
      <p className="max-w-xl text-lg text-zinc-600 dark:text-zinc-400">
        Upload your resume once. Every day the agent pulls new remote roles, explains why each one does or does not fit your real experience, and tailors your application without inventing a single claim.
      </p>
      <div className="flex gap-3">
        <Link href="/register"><Button>Create account</Button></Link>
        <Link href="/login"><Button variant="secondary">Log in</Button></Link>
      </div>
    </div>
  );
}
