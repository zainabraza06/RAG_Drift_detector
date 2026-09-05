import { Activity, LayoutGrid, ListChecks, Menu, Radar, TrendingUp, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { HealthDot } from "@/components/HealthBadge";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { IconButton } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { useDashboard } from "@/lib/queries";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/trends", label: "Trends", icon: TrendingUp },
  { to: "/drift", label: "Drift events", icon: Radar },
  { to: "/golden-set", label: "Golden set", icon: ListChecks },
];

const SIDEBAR_WIDTH = "w-[248px]";

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Navigating on mobile dismisses the drawer; leaving it open would hide the
  // page the user just asked for.
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen bg-app">
      <div
        onClick={() => setMobileOpen(false)}
        aria-hidden
        className={cn(
          "fixed inset-0 z-30 bg-black/40 backdrop-blur-[2px] transition-opacity duration-slow lg:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      <Sidebar
        className={cn(
          "fixed inset-y-0 left-0 z-40 transition-transform duration-slow ease-out lg:translate-x-0",
          SIDEBAR_WIDTH,
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        onClose={() => setMobileOpen(false)}
        showClose={mobileOpen}
      />

      <div className="lg:pl-[248px]">
        <TopBar onOpenMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-content px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Sidebar({
  className,
  onClose,
  showClose,
}: {
  className?: string;
  onClose: () => void;
  showClose: boolean;
}) {
  const { data } = useDashboard();

  return (
    <aside className={cn("flex flex-col border-r border-line bg-surface", className)}>
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded bg-accent">
            <Activity className="h-3.5 w-3.5 text-accent-fg" aria-hidden />
          </span>
          <span className="truncate text-subheading text-ink">Drift Detector</span>
        </div>
        {showClose ? (
          <IconButton
            aria-label="Close navigation"
            size="sm"
            className="lg:hidden"
            icon={<X className="h-4 w-4" aria-hidden />}
            onClick={onClose}
          />
        ) : null}
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5",
                "text-small font-medium transition-colors duration-fast ease-out",
                isActive
                  ? "bg-inset text-ink"
                  : "text-ink-secondary hover:bg-surface-hover hover:text-ink",
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    isActive ? "text-accent" : "text-ink-tertiary",
                  )}
                  aria-hidden
                />
                {item.label}
                {item.to === "/drift" && data?.open_regressions ? (
                  <span className="tnum ml-auto rounded-sm bg-danger-subtle px-1.5 py-0.5 text-micro text-danger-text">
                    {data.open_regressions}
                  </span>
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <ActiveGoldenSetSummary />
    </aside>
  );
}

function ActiveGoldenSetSummary() {
  const { data } = useDashboard();
  const active = data?.active_golden_set;

  return (
    <div className="border-t border-line-subtle px-5 py-4">
      <p className="text-micro uppercase text-ink-tertiary">Active golden set</p>
      {active ? (
        <>
          <p className="mt-1.5 truncate text-small font-medium text-ink">
            {active.golden_set.name}
          </p>
          <p className="tnum mt-0.5 text-label text-ink-tertiary">
            v{active.golden_set.version} · {active.golden_set.queries.length} queries
          </p>
        </>
      ) : (
        <p className="mt-1.5 text-label text-ink-tertiary">None selected</p>
      )}
    </div>
  );
}

function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { data } = useDashboard();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-app/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-content items-center gap-3 px-5 sm:px-8 lg:px-10">
        <IconButton
          aria-label="Open navigation"
          size="sm"
          className="lg:hidden"
          icon={<Menu className="h-4 w-4" aria-hidden />}
          onClick={onOpenMenu}
        />

        {data ? (
          <div className="flex min-w-0 items-center gap-2">
            <HealthDot status={data.health} />
            <span className="tnum truncate text-small text-ink-secondary">
              {data.has_runs
                ? `${data.total_runs} run${data.total_runs === 1 ? "" : "s"}`
                : "No evaluations yet"}
            </span>
          </div>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <RunEvaluationButton size="sm" variant="secondary" compactOnMobile />
        </div>
      </div>
    </header>
  );
}
