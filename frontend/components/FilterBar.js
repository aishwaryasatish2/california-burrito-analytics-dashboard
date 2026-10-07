"use client";

import { useEffect, useId, useRef, useState } from "react";

import { hasActiveFilters } from "@/lib/filters";

const MULTI_SELECTS = [
  { key: "outlet", label: "Outlet", options: "outlets" },
  { key: "group", label: "Menu group", options: "groups" },
  { key: "order_type", label: "Order type", options: "order_types" },
  { key: "settlement", label: "Channel / settlement", options: "settlements" },
];

export default function FilterBar({ filters, options, onChange, onReset, loading, rangeError }) {
  return (
    <section className="filter-bar" aria-label="Filters">
      <div className="filter-row">
        <div className="field">
          <label htmlFor="filter-start">From</label>
          <input id="filter-start" type="date" value={filters.start}
                 min={options?.min_date} max={options?.max_date}
                 onChange={(e) => onChange({ start: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="filter-end">To</label>
          <input id="filter-end" type="date" value={filters.end}
                 min={options?.min_date} max={options?.max_date}
                 onChange={(e) => onChange({ end: e.target.value })} />
        </div>

        {MULTI_SELECTS.map(({ key, label, options: optionKey }) => (
          <MultiSelect key={key} label={label} options={options?.[optionKey] ?? []}
                       selected={filters[key]} onChange={(values) => onChange({ [key]: values })} />
        ))}

        <div className="filter-actions">
          <button type="button" className="button" onClick={onReset} disabled={!hasActiveFilters(filters)}>
            Reset filters
          </button>
          <span className="status" role="status" aria-live="polite">
            {loading ? "Updating…" : ""}
          </span>
        </div>
      </div>
      {rangeError && <p className="field-error" role="alert">{rangeError} Choose an end date on or after the start date.</p>}
    </section>
  );
}

function MultiSelect({ label, options, selected, onChange }) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const buttonRef = useRef(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event) => {
      if (!wrapperRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  const toggle = (value) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  const summary = selected.length === 0 ? "All"
    : selected.length === 1 ? selected[0]
    : `${selected.length} selected`;

  return (
    <div
      className="field"
      ref={wrapperRef}
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          setOpen(false);
          buttonRef.current?.focus();
        }
      }}
      onBlur={(e) => {
        if (!wrapperRef.current?.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <span className="field-label" id={`${id}-label`}>{label}</span>
      <button
        ref={buttonRef}
        type="button"
        className={`select-button${selected.length ? " has-value" : ""}`}
        aria-expanded={open}
        aria-controls={`${id}-panel`}
        aria-labelledby={`${id}-label ${id}-value`}
        onClick={() => setOpen((o) => !o)}
        disabled={options.length === 0}
      >
        <span id={`${id}-value`}>{summary}</span>
        <span className="chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="select-panel" id={`${id}-panel`} role="group" aria-labelledby={`${id}-label`}>
          {options.map((option) => (
            <label key={option} className="check">
              <input type="checkbox" checked={selected.includes(option)} onChange={() => toggle(option)} />
              {option}
            </label>
          ))}
          <button type="button" className="link-button" onClick={() => onChange([])}
                  disabled={selected.length === 0}>
            Clear {label.toLowerCase()}
          </button>
        </div>
      )}
    </div>
  );
}
