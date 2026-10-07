import { Suspense } from "react";

import Dashboard from "@/components/Dashboard";

// useSearchParams (URL filter state) requires a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={<p className="placeholder">Loading dashboard…</p>}>
      <Dashboard />
    </Suspense>
  );
}
