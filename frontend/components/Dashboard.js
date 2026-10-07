"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { fetchDashboard, fetchFilterOptions } from "@/lib/api";
import { dateRangeError, readFilters, sanitizeFilters, toQueryString } from "@/lib/filters";
import { formatCount, formatLongDate, formatRupeesPrecise } from "@/lib/format";
import FilterBar from "./FilterBar";
import KpiStrip from "./KpiStrip";
import TrendChart from "./TrendChart";
import RankedBars from "./RankedBars";
import OrderTypePanel from "./OrderTypePanel";
import HourlyChart from "./HourlyChart";
import TopItemsTable from "./TopItemsTable";

// Business name shown as page context. The dataset's own Brand column holds a
// different single value; it is not used for display or filtering.
const BRAND = "California Burrito";
const DEBOUNCE_MS = 250;

export default function Dashboard() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Filters live in React state (initialised from the URL) so controls update
  // instantly; the URL mirrors them so a view can be shared or bookmarked.
  const [filters, setFilters] = useState(() => readFilters(searchParams));
  const queryString = toQueryString(filters);
  const rangeError = dateRangeError(filters);

  const [options, setOptions] = useState(null);
  const [optionsError, setOptionsError] = useState(null);
  const [optionsAttempt, setOptionsAttempt] = useState(0); // bumped by its "Try again"
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0); // bumped by "Try again"
  const isFirstRequest = useRef(true);

  const updateFilters = useCallback((patch) => {
    setFilters((current) => ({ ...current, ...patch }));
  }, []);

  // Mirror filters into the URL. replaceState: no navigation or server round
  // trip, and no history entry per click.
  useEffect(() => {
    window.history.replaceState(null, "", queryString ? `${pathname}?${queryString}` : pathname);
  }, [queryString, pathname]);

  const resetFilters = useCallback(() => {
    // Keep the chosen granularity; it is a chart setting, not a filter.
    updateFilters({ start: "", end: "", outlet: [], group: [], order_type: [], settlement: [] });
  }, [updateFilters]);

  // Filter options load first: they populate the controls and are used to
  // drop URL values that don't exist in the data before any dashboard request.
  useEffect(() => {
    const controller = new AbortController();
    setOptionsError(null);
    fetchFilterOptions(controller.signal)
      .then((result) => {
        setOptions(result);
        setFilters((current) => sanitizeFilters(current, result));
      })
      .catch((e) => e.name !== "AbortError" && setOptionsError(e.message));
    return () => controller.abort();
  }, [optionsAttempt]);

  useEffect(() => {
    if (!options) return; // wait until URL filters have been checked against the data
    if (rangeError) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    // Debounce so quick successive filter changes send one request; the
    // first load is not delayed.
    const delay = isFirstRequest.current ? 0 : DEBOUNCE_MS;
    isFirstRequest.current = false;
    const timer = setTimeout(() => {
      fetchDashboard(queryString, controller.signal)
        .then((result) => {
          setData(result);
          setError(null);
          setLoading(false);
        })
        .catch((e) => {
          if (e.name === "AbortError") return;
          setError(e.message);
          setLoading(false);
        });
    }, delay);
    return () => {
      clearTimeout(timer);
      controller.abort(); // a newer filter state supersedes this request
    };
  }, [queryString, rangeError, attempt, options]);

  const retry = () => setAttempt((n) => n + 1);
  const retryOptions = () => setOptionsAttempt((n) => n + 1);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Business analytics dashboard</h1>
        <p className="page-subtitle">
          {options
            ? `${BRAND} sales across ${options.outlets.length} outlets, ${formatLongDate(options.min_date)} to ${formatLongDate(options.max_date)}.`
            : `${BRAND} sales.`}
        </p>
      </header>

      <FilterBar
        filters={filters}
        options={options}
        onChange={updateFilters}
        onReset={resetFilters}
        loading={loading && Boolean(data)}
        rangeError={rangeError}
      />

      <main className={`content${loading && data ? " is-updating" : ""}`} aria-busy={loading}>
        {optionsError && (
          <div className="notice notice-error" role="alert">
            <p>Couldn&apos;t load the filter options, so the dashboard can&apos;t be shown yet. {optionsError}</p>
            <button type="button" className="button" onClick={retryOptions}>Try again</button>
          </div>
        )}

        {error && (
          <div className="notice notice-error" role="alert">
            <p>
              {data ? "Couldn't refresh the dashboard. Showing the last loaded results. " : "Couldn't load the dashboard. "}
              {error}
            </p>
            <button type="button" className="button" onClick={retry}>Try again</button>
          </div>
        )}

        {rangeError ? (
          // Don't leave earlier results on screen looking current.
          <p className="placeholder">Choose a valid date range to see results.</p>
        ) : (
          <>
            {!data && !error && !optionsError && <p className="placeholder">Loading dashboard…</p>}
            {data && <DashboardBody data={data} filters={filters} options={options}
                                    onChange={updateFilters} onReset={resetFilters} />}
          </>
        )}
      </main>
    </div>
  );
}

function DashboardBody({ data, filters, options, onChange, onReset }) {
  const { kpis, scope } = data;

  if (kpis.orders === 0) {
    return (
      <div className="empty-state">
        <p>No data for the selected filters.</p>
        <p className="muted">No orders match this combination of dates and filters.</p>
        <button type="button" className="button" onClick={onReset}>Reset filters</button>
      </div>
    );
  }

  return (
    <>
      <KpiStrip kpis={kpis} />
      {scope.line_level_filter && (
        <p className="scope-note">
          Menu group filter ({scope.groups.join(", ")}): metrics reflect only the matching lines
          of orders containing the selected {scope.groups.length > 1 ? "groups" : "group"}, not
          whole bills. AOV is calculated on matching positive-revenue orders.
        </p>
      )}

      <TrendChart
        trend={data.trend}
        granularity={filters.granularity}
        onGranularityChange={(granularity) => onChange({ granularity })}
        dataRange={options}
      />

      <div className="grid-2">
        <RankedBars
          title="Gross revenue by outlet"
          rows={data.by_outlet.map((r) => ({
            label: r.outlet,
            value: r.revenue,
            details: [`${formatCount(r.orders)} orders`, r.aov != null ? `AOV ${formatRupeesPrecise(r.aov)}` : null],
          }))}
          total={kpis.gross_revenue}
        />
        <RankedBars
          title="Gross revenue by menu group"
          rows={data.by_group.map((r) => ({
            label: r.group,
            value: r.revenue,
            details: [`${formatCount(r.units)} units`],
          }))}
          total={kpis.gross_revenue}
        />
      </div>

      <div className="grid-2">
        <OrderTypePanel orderTypes={data.by_order_type} channels={data.channels} />
        <HourlyChart hourly={data.hourly} totalOrders={kpis.orders} />
      </div>

      <TopItemsTable items={data.top_items} />
    </>
  );
}
