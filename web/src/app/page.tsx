import { ApiStatus } from "@/components/api-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6 py-16">
      <p className="text-sm font-medium uppercase tracking-wide text-zinc-500">JobHunt Copilot</p>
      <h1 className="text-4xl font-semibold tracking-tight">
        Find remote jobs you are actually a fit for.
      </h1>
      <p className="max-w-xl text-lg text-zinc-600 dark:text-zinc-400">
        Upload your resume once. Every day the agent pulls new remote roles, explains why each one
        does or does not fit your real experience, and tailors your application without inventing
        a single claim.
      </p>
      <ApiStatus />
    </main>
  );
}
