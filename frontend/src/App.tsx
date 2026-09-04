import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ChartSkeleton, ListSkeleton } from "@/components/states/LoadingState";
import { ToastProvider } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { DashboardPage } from "@/pages/DashboardPage";

// Recharts is by far the heaviest dependency and only the trends view needs
// it, so the routes that pull it in are split out of the initial bundle.
const TrendsPage = lazy(() =>
  import("@/pages/TrendsPage").then((m) => ({ default: m.TrendsPage })),
);
const DriftEventsPage = lazy(() =>
  import("@/pages/DriftEventsPage").then((m) => ({ default: m.DriftEventsPage })),
);
const GoldenSetPage = lazy(() =>
  import("@/pages/GoldenSetPage").then((m) => ({ default: m.GoldenSetPage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/NotFoundPage").then((m) => ({ default: m.NotFoundPage })),
);

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      // A 404 or a validation error will not fix itself; only retry the
      // failures where retrying is meaningful.
      retry: (failureCount, error) =>
        error instanceof ApiError && !error.isTransient ? false : failureCount < 2,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route
                path="trends"
                element={
                  <Suspense fallback={<RouteFallback variant="charts" />}>
                    <TrendsPage />
                  </Suspense>
                }
              />
              <Route
                path="drift"
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <DriftEventsPage />
                  </Suspense>
                }
              />
              <Route
                path="golden-set"
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <GoldenSetPage />
                  </Suspense>
                }
              />
              <Route
                path="*"
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <NotFoundPage />
                  </Suspense>
                }
              />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

/** Shaped like the route it stands in for, so the layout does not jump. */
function RouteFallback({ variant }: { variant?: "charts" }) {
  if (variant === "charts") {
    return (
      <div className="grid gap-4 xl:grid-cols-2">
        {[0, 1, 2, 3].map((index) => (
          <ChartSkeleton key={index} />
        ))}
      </div>
    );
  }
  return <ListSkeleton />;
}
