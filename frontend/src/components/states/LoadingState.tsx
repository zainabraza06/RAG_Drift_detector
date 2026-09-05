import { Skeleton } from "@/components/ui/Skeleton";

/** Shaped like the stat row it replaces, so nothing shifts on arrival. */
export function StatCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="rounded-lg border border-line bg-surface px-5 py-4">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="mt-4 h-7 w-24" />
          <Skeleton className="mt-3 h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 200 }: { height?: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-5 py-4">
      <Skeleton className="h-3.5 w-24" />
      <Skeleton className="mt-2 h-3 w-56" />
      <Skeleton className="mt-5 w-full rounded-md" style={{ height }} />
    </div>
  );
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="rounded-lg border border-line bg-surface px-5 py-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-4 w-20 rounded" />
            <Skeleton className="h-3 w-24" />
          </div>
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-3/4" />
        </div>
      ))}
    </div>
  );
}
