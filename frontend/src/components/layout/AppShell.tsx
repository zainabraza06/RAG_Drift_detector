import {
  Activity,
  LayoutDashboard,
  ListChecks,
  Menu,
  Radar,
  TrendingUp,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { HealthDot } from "@/components/HealthBadge";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { cn } from "@/lib/cn";
import { useDashboard } from "@/lib/queries";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/trends", label: "Trends", icon: TrendingUp },
  { to: "/drift", label: "Drift events", icon: Radar },
  { to: "/golden-set", label: "Golden set", icon: ListChecks },
];

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Navigating on mobile should dismiss the drawer; leaving it open hides the
  // page the user just asked for.
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen bg-canvas">
      <MobileOverlay open={mobileOpen} onClose={() => setMobileOpen(false)} />

      <Sidebar
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 transition-transform duration-300 ease-out lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        onClose={() => setMobileOpen(false)}
        showClose={mobileOpen}
      />

      <div className="lg:pl-64">
        <TopBar onOpenMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[88rem] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MobileOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      aria-hidden
      className={cn(
        "fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-sm transition-opacity duration-300 lg:hidden",
        open ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    />
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
    <aside
      className={cn(
        "flex flex-col border-r border-line bg-surface",
        className,
      )}
    >
      <div className="flex h-14 items-center justify-between gap-2 border-b border-line px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand">
            <Activity className="h-4 w-4 text-brand-fg" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-tight text-content">
              Drift Detector
            </p>
            <p className="truncate text-2xs leading-tight text-content-subtle">
              Retrieval quality
            </p>
          </div>
        </div>
        {showClose ? (
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-md p-1 text-content-muted hover:bg-surface-muted lg:hidden"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        ) : null}
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium",
                "transition-colors duration-150",
                isActive
                  ? "bg-brand-soft text-brand"
                  : "text-content-muted hover:bg-surface-muted hover:text-content",
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform duration-150",
                    !isActive && "group-hover:scale-110",
                  )}
                  aria-hidden
                />
                {item.label}
                {item.to === "/drift" && data?.open_regressions ? (
                  <span className="tnum ml-auto rounded-full bg-critical px-1.5 py-0.5 text-2xs font-semibold text-white">
                    {data.open_regressions}
                  </span>
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-line p-3">
        <ActiveGoldenSetSummary />
      </div>
    </aside>
  );
}

function ActiveGoldenSetSummary() {
  const { data } = useDashboard();
  const active = data?.active_golden_set;

  if (!active) {
    return (
      <p className="px-2 text-2xs leading-relaxed text-content-subtle">
        No active golden set.
      </p>
    );
  }

  return (
    <div className="rounded-lg bg-surface-muted px-3 py-2.5">
      <p className="text-2xs font-medium uppercase tracking-wide text-content-subtle">
        Active golden set
      </p>
      <p className="mt-1 truncate text-xs font-medium text-content">
        {active.golden_set.name}
      </p>
      <p className="mt-0.5 text-2xs text-content-subtle">
        v{active.golden_set.version} · {active.golden_set.queries.length} queries
      </p>
    </div>
  );
}

function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { data } = useDashboard();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-[88rem] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          onClick={onOpenMenu}
          aria-label="Open navigation"
          className="rounded-md p-1.5 text-content-muted transition-colors hover:bg-surface-muted hover:text-content lg:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>

        {data ? (
          <div className="flex min-w-0 items-center gap-2">
            <HealthDot status={data.health} />
            <span className="truncate text-sm text-content-muted">
              {data.has_runs
                ? `${data.total_runs} run${data.total_runs === 1 ? "" : "s"} recorded`
                : "No evaluations yet"}
            </span>
          </div>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <RunEvaluationButton size="sm" />
        </div>
      </div>
    </header>
  );
}
