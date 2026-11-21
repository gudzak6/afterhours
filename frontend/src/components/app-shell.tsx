"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "cn";

const coachLinks = [
  { href: "/", label: "Dashboard" },
  { href: "/athletes", label: "Athletes" },
  { href: "/agent", label: "Agent" },
  { href: "/plan", label: "Plans" },
  { href: "/settings", label: "Settings" },
];

const athleteLinks = [
  { href: "/athlete", label: "Home" },
  { href: "/athlete/calendar", label: "Calendar" },
  { href: "/athlete/week", label: "Plan" },
  { href: "/athlete/analytics", label: "Analytics" },
  { href: "/athlete/messages", label: "Coach Owen" },
  { href: "/athlete/settings", label: "Settings" },
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
  const links = coachSide ? coachLinks : athleteSide ? athleteLinks : [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-foreground/15 bg-background">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <Link href={coachSide ? "/" : "/athlete"} className="inline-flex shrink-0">
            <img src="/after-hours-athletics.png" alt="after : hours athletics" className="h-9 w-auto sm:h-11" />
          </Link>
          <nav className="-mx-1 flex items-center gap-1 overflow-x-auto px-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {links.map((link) => {
              const active = isActive(pathname, link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "shrink-0 px-1.5 py-2 text-[11px] tracking-[0.08em] uppercase sm:px-2.5 sm:tracking-[0.14em]",
                    active ? "text-foreground underline decoration-1 underline-offset-8" : "text-foreground/70 hover:text-foreground",
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-6">{children}</main>
      <footer className="border-t border-foreground/15">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 sm:px-6">
          <p className="text-[11px] tracking-[0.16em] uppercase">after : hours athletics</p>
          <p className="text-sm text-muted-foreground">Personalized coaching for performance driven running.</p>
        </div>
      </footer>
    </div>
  );
}
