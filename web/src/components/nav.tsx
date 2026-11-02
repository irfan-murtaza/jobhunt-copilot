"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui";

const links = [
  { href: "/matches", label: "Matches" },
  { href: "/jobs", label: "Jobs" },
  { href: "/tracker", label: "Tracker" },
  { href: "/profile", label: "Profile" },
  { href: "/preferences", label: "Preferences" },
];

export function Nav() {
  const { user, logout } = useAuth();
  const path = usePathname();
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-semibold tracking-tight">JobHunt Copilot</Link>
          {user && (
            <nav className="flex gap-1 text-sm">
              {links.map((l) => (
                <Link key={l.href} href={l.href} className={`rounded-md px-3 py-1.5 ${path.startsWith(l.href) ? "bg-zinc-100 font-medium dark:bg-zinc-800" : "text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}>
                  {l.label}
                </Link>
              ))}
            </nav>
          )}
        </div>
        <div className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              <span className="text-zinc-500">{user.display_name ?? user.email}</span>
              <Button variant="ghost" size="sm" onClick={logout}>Log out</Button>
            </>
          ) : (
            <Link href="/login" className="text-zinc-600 hover:underline">Log in</Link>
          )}
        </div>
      </div>
    </header>
  );
}
