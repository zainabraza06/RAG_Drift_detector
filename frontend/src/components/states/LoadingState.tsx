import { Skeleton } from "@/components/ui/Skeleton";

/** Placeholder shaped like the stat card row it replaces. */
export function StatCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="rounded-xl border border-line bg-surface p-5">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-4 h-8 w-24" />
          <Skeleton className="mt-3 h-3 w-16" />
        </div>
      ))}
    </div>
  );
}

/** Placeholder shaped like a chart panel. */
export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="mt-5 w-full rounded-lg" style={{ height }} />
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="rounded-xl border border-line bg-surface p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-20 rounded-md" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="mt-4 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-4/5" />
        </div>
      ))}
    </div>
  );
}
