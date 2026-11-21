"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { cn } from "cn";
import { accountEmail } from "@/lib/account";

const coachLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/athletes", label: "Athletes" },
  { href: "/agent", label: "Agent" },
  { href: "/plan", label: "Plan" },
  { href: "/settings", label: "Settings" },
];

const athleteLinks = [
  { href: "/athlete", label: "Home" },
  { href: "/athlete/calendar", label: "Calendar" },
  { href: "/athlete/week", label: "Plan" },
  { href: "/athlete/analytics", label: "Analytics" },
  { href: "/athlete/messages", label: "Coach" },
];

function isActive(pathname: string, href: string) {
  if (href === "/" || href === "/athlete") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function isCoachPath(pathname: string) {
  return (
    pathname === "/" ||
    pathname.startsWith("/athletes") ||
    pathname.startsWith("/agent") ||
    pathname.startsWith("/plan") ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/activities") ||
    pathname.startsWith("/coach")
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const coachSide = isCoachPath(pathname);
  const athleteSide = pathname === "/athlete" || pathname.startsWith("/athlete/");
  const [email, setEmail] = useState<string | null>(null);
  const links = coachSide ? coachLinks : athleteSide ? athleteLinks : [];

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void accountEmail().then(setEmail).catch(() => setEmail(null));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pathname]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-medium tracking-[0.16em] text-primary uppercase">
              {coachSide ? "Local running coach" : "Your training"}
            </p>
            <Link href={coachSide ? "/" : "/athlete"} className="font-heading text-2xl tracking-tight">
              Training Coach
            </Link>
          </div>
          <nav className="flex flex-wrap items-center gap-1">
            {coachSide ? null : (
              <Link
                href="/login"
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm",
                  pathname === "/login" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {email ?? "Account"}
              </Link>
            )}
            {links.map((link) => {
              const active = isActive(pathname, link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm",
                    active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
      {athleteSide ? (
        <Link
          href="/"
          className="fixed right-4 bottom-4 z-40 rounded-full bg-primary px-4 py-2 text-sm text-primary-foreground shadow-lg"
        >
          Coach view
        </Link>
      ) : null}
    </div>
  );
}
