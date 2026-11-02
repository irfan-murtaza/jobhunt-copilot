import { fetchHealth } from "@/lib/api";

export async function ApiStatus() {
  const health = await fetchHealth();
  const ok = health?.status === "ok";
  return (
    <div className="flex items-center gap-2 text-sm text-zinc-500">
      <span
        aria-hidden
        className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-zinc-400"}`}
      />
      {ok ? `API connected (v${health?.version})` : "API not reachable"}
    </div>
  );
}
