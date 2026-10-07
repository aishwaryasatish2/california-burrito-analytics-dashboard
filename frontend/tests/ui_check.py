"""Browser checks for the dashboard (Playwright, headless Chromium).

Every KPI shown on screen is compared with a direct call to the API using the
same query string, so the test verifies the page shows what the API returns
(no hardcoded dashboard numbers).

Needs the API (default http://localhost:8000) and the built frontend
(default http://localhost:3000) running.

    pip install playwright && playwright install chromium
    python tests/ui_check.py [--app URL] [--api URL] [--shots DIR]
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}{f'  ({detail})' if detail and not condition else ''}")


def api_json(api, query):
    with urllib.request.urlopen(f"{api}/api/dashboard?{query}") as response:
        return json.load(response)


def number(text):
    return float(re.sub(r"[^\d.]", "", text))


def wait_for_dashboard(page):
    page.wait_for_selector(".content:not(.is-updating) .kpi-strip, .content:not(.is-updating) .empty-state")


def displayed_kpis(page):
    values = {}
    for kpi in page.locator(".kpi").all():
        label = kpi.locator("dt").inner_text()
        values[label] = (kpi.locator(".kpi-value").inner_text(), kpi.locator(".kpi-note").inner_text())
    return values


def kpis_match_api(page, api, label):
    """Compare every on-screen KPI with the API response for the page's own URL."""
    wait_for_dashboard(page)
    query = urllib.parse.urlparse(page.url).query
    expected = api_json(api, query)["kpis"]
    shown = displayed_kpis(page)
    mismatches = []
    if int(number(shown["Gross revenue"][1].split(" at ")[0])) != expected["gross_revenue"]:
        mismatches.append("gross revenue")
    if int(number(shown["Orders"][0])) != expected["orders"]:
        mismatches.append("orders")
    if expected["aov"] is not None and number(shown["Average order value"][0]) != expected["aov"]:
        mismatches.append("aov")
    if int(number(shown["Units sold"][0])) != expected["units_sold"]:
        mismatches.append("units")
    if number(shown["Items per order"][0]) != expected["items_per_order"]:
        mismatches.append("items per order")
    if int(number(shown["Items per order"][1])) != expected["line_items"]:
        mismatches.append("line items")
    check(f"{label}: displayed KPIs equal API (?{query or 'no filters'})", not mismatches, ", ".join(mismatches))
    return expected


def choose(page, filter_label, option):
    # Plain substring match: a "/" in a label breaks Playwright's regex serialisation.
    page.get_by_role("button", name=filter_label).click()
    page.get_by_role("checkbox", name=option, exact=True).check()
    page.keyboard.press("Escape")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://localhost:3000")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--shots", default=None, help="directory for screenshots")
    args = parser.parse_args()
    app, api = args.app, args.api
    shots = Path(args.shots) if args.shots else None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # Initial load
        page.goto(app)
        totals = kpis_match_api(page, api, "Initial load")
        top_items = [r.inner_text() for r in page.locator(".top-items tbody th").all()]
        check("Top items listed in API order", top_items == [i["item"] for i in api_json(api, "")["top_items"]])
        # Recharts 3 draws tick labels in a separate layer, not inside .recharts-yAxis.
        ticks = page.locator('section[aria-label="Gross revenue by outlet"] .recharts-yAxis-tick-labels .recharts-cartesian-axis-tick-value')
        ticks.first.wait_for(state="attached")  # charts render after ResponsiveContainer measures its width
        outlets = ticks.all_text_contents()
        check("Outlet bars sorted by revenue", outlets == [r["outlet"] for r in api_json(api, "")["by_outlet"]])
        check("Weekly is the default granularity",
              page.get_by_role("button", name="Weekly").get_attribute("aria-pressed") == "true")
        check("Partial-week note shown", page.locator(".chart-note", has_text="Partial week").count() == 1)
        check("No scope note without a group filter", page.locator(".scope-note").count() == 0)
        page_text = page.locator("body").inner_text()
        check("Branding shows California Burrito, not Burger Town",
              "California Burrito" in page.locator(".page-subtitle").inner_text() and "Burger Town" not in page_text)
        check("Page title uses California Burrito", page.title() == "California Burrito sales dashboard")
        check("No 24:00 hour label anywhere", "24:00" not in page_text
              and "24:00" not in (page.locator("section[aria-labelledby=hourly-title] [role=img]").get_attribute("aria-label") or ""))
        check("Channel table is inside a horizontal scroll wrapper",
              page.locator(".table-scroll > .channel-table").count() == 1)
        trend_label = page.locator("section[aria-labelledby=trend-title] [role=img]").get_attribute("aria-label")
        check("Trend summary states ranges and excludes partial weeks",
              "ranged from" in trend_label and "partial weeks are excluded" in trend_label, trend_label)
        outlet_label = page.locator('section[aria-label="Gross revenue by outlet"] [role=img]').get_attribute("aria-label")
        check("Outlet summary lists every outlet",
              all(r["outlet"] in outlet_label for r in api_json(api, "")["by_outlet"]), outlet_label)
        if shots:
            page.screenshot(path=str(shots / "desktop-1366.png"), full_page=True)

        # Each filter on its own
        for label, option, param in [("Outlet", "Koramangala", "outlet"), ("Order type", "Delivery", "order_type"),
                                     ("Channel / settlement", "Dineout", "settlement")]:
            page.goto(app)
            wait_for_dashboard(page)
            choose(page, label, option)
            page.wait_for_url(re.compile(f"{param}="))
            kpis_match_api(page, api, f"{label} filter")

        # Group filter and scope note
        page.goto(app)
        wait_for_dashboard(page)
        choose(page, "Menu group", "Drinks")
        page.wait_for_url(re.compile("group=Drinks"))
        drinks = kpis_match_api(page, api, "Menu group filter")
        check("Scope note shown for group filter",
              page.locator(".scope-note").is_visible() and "Drinks" in page.locator(".scope-note").inner_text())
        check("Group-filtered revenue is below the total", drinks["gross_revenue"] < totals["gross_revenue"])
        if shots:
            page.screenshot(path=str(shots / "group-filter.png"), full_page=False)

        # Multiple filters, via URL (also proves the URL restores state)
        page.goto(f"{app}/?start=2025-10-01&end=2025-12-31&outlet=Indiranagar&outlet=Koramangala"
                  f"&group=Burgers&group=Sides&order_type=Delivery")
        kpis_match_api(page, api, "Multiple filters from URL")
        check("URL state restored into controls",
              page.get_by_role("button", name=re.compile("^Outlet")).inner_text().startswith("2 selected")
              and page.locator("#filter-start").input_value() == "2025-10-01")

        # Invalid URL values are dropped, not shown as selected or sent to the API
        page.goto(f"{app}/?outlet=Atlantis&outlet=MG%20Road&group=Pizza&start=2026-02-30")
        wait_for_dashboard(page)
        page.wait_for_url(lambda url: "Atlantis" not in url)
        check("Invalid URL values are removed from the URL",
              "Pizza" not in page.url and "start=" not in page.url and "outlet=MG+Road" in page.url, page.url)
        check("Invalid URL values are not shown as selected",
              page.get_by_role("button", name=re.compile("^Outlet")).inner_text().startswith("MG Road")
              and page.get_by_role("button", name=re.compile("^Menu group")).inner_text().startswith("All"))
        check("Invalid URL values cause no error", page.locator(".notice-error").count() == 0)
        kpis_match_api(page, api, "Sanitized URL")

        # Reset
        page.get_by_role("button", name="Reset filters").click()
        page.wait_for_url(re.compile(r"^[^?]*$"))
        after_reset = kpis_match_api(page, api, "Reset")
        check("Reset restores the unfiltered totals", after_reset == totals)
        check("Reset is disabled with no filters", page.get_by_role("button", name="Reset filters").is_disabled())

        # Date boundaries: a single day includes orders up to 23:59
        page.goto(f"{app}/?start=2026-01-15&end=2026-01-15&granularity=day")
        day = kpis_match_api(page, api, "Single-day range")
        check("Single day returns one daily point",
              len(api_json(api, "start=2026-01-15&end=2026-01-15&granularity=day")["trend"]["points"]) == 1
              and day["orders"] > 0)

        page.goto(f"{app}/?start=2025-06-17&end=2026-06-16")
        kpis_match_api(page, api, "Full data range given explicitly")

        # Start after end: no request, clear message
        page.goto(app)
        wait_for_dashboard(page)
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/api/dashboard" in r.url else None)
        page.locator("#filter-start").fill("2026-03-10")
        page.locator("#filter-end").fill("2026-03-01")
        page.wait_for_timeout(800)
        check("Start after end shows an error", page.get_by_text("The start date is after the end date").is_visible())
        check("Start after end sends no request for the invalid range",
              not any("start=2026-03-10&end=2026-03-01" in r for r in requests))
        check("Start after end hides the previous results", page.locator(".kpi-strip").count() == 0)

        # No data
        page.goto(f"{app}/?order_type=Delivery&settlement=Dineout")
        wait_for_dashboard(page)
        check("No-data message for an impossible combination",
              page.get_by_text("No data for the selected filters.").is_visible()
              and page.locator(".kpi-strip").count() == 0)
        body = page.locator("main").inner_text()
        check("No NaN/undefined anywhere in the empty state", "NaN" not in body and "undefined" not in body)

        # Day / week toggle
        page.goto(app)
        wait_for_dashboard(page)
        page.get_by_role("button", name="Daily").click()
        page.wait_for_url(re.compile("granularity=day"))
        wait_for_dashboard(page)
        check("Daily toggle updates URL and hides partial-week note",
              page.locator(".chart-note", has_text="Partial week").count() == 0)
        page.get_by_role("button", name="Weekly").click()
        page.wait_for_url(re.compile(r"^[^?]*$"))
        check("Weekly toggle returns to the default URL", "granularity" not in page.url)

        # Debounce: three quick selections produce one request
        page.goto(app)
        wait_for_dashboard(page)
        requests.clear()
        page.get_by_role("button", name="Outlet").click()
        # Click three checkboxes inside the page in one tick, so the test measures the
        # debounce rather than Playwright's (machine-dependent) delay between clicks.
        page.evaluate("""() => {
            for (const name of ["MG Road", "JP Nagar", "Whitefield"]) {
                [...document.querySelectorAll(".select-panel label")]
                    .find((l) => l.textContent.trim() === name).querySelector("input").click();
            }
        }""")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        check("Rapid filter changes are debounced into one request",
              len(requests) == 1 and all(o in requests[0] for o in ["MG+Road", "JP+Nagar", "Whitefield"]),
              f"{len(requests)} requests: {requests}")

        # Loading state: previous dashboard stays visible
        page.goto(app)
        wait_for_dashboard(page)
        held = []  # hold the request open so the loading state can be observed
        page.route("**/api/dashboard*", lambda route: held.append(route))
        choose(page, "Outlet", "HSR Layout")
        page.wait_for_selector(".content.is-updating")
        page.wait_for_timeout(600)  # past the debounce, request now pending
        check("While loading: previous KPIs stay visible", page.locator(".kpi-strip").is_visible())
        check("While loading: status says Updating", page.get_by_role("status").inner_text() == "Updating…")
        if shots:
            page.screenshot(path=str(shots / "loading.png"))
        for route in held:  # release the held request first, then remove the handler
            route.continue_()
        page.unroute("**/api/dashboard*")
        wait_for_dashboard(page)

        # API failure after a successful load
        page.route("**/api/dashboard*", lambda route: route.abort())
        choose(page, "Outlet", "MG Road")
        page.wait_for_selector(".notice-error")
        check("API failure: error message with retry, old results kept",
              page.get_by_role("button", name="Try again").is_visible() and page.locator(".kpi-strip").is_visible())
        page.unroute("**/api/dashboard*")
        page.get_by_role("button", name="Try again").click()
        page.wait_for_selector(".notice-error", state="detached")
        kpis_match_api(page, api, "Recovered after retry")

        # /api/filters failure has its own message and retry
        page.route("**/api/filters*", lambda route: route.abort())
        page.goto(app)
        page.wait_for_selector(".notice-error")
        check("Filter-options failure: clear message",
              "filter options" in page.locator(".notice-error").inner_text())
        page.unroute("**/api/filters*")
        page.get_by_role("button", name="Try again").click()
        page.wait_for_selector(".notice-error", state="detached")
        kpis_match_api(page, api, "Recovered after filter-options retry")
        check("Filter controls enabled after options recover",
              page.get_by_role("button", name=re.compile("^Outlet")).is_enabled())

        # Keyboard: open, toggle, close with Escape, focus returns
        page.goto(app)
        wait_for_dashboard(page)
        button = page.get_by_role("button", name=re.compile("^Menu group"))
        button.focus()
        page.keyboard.press("Enter")
        check("Keyboard: Enter opens the multi-select", button.get_attribute("aria-expanded") == "true")
        page.keyboard.press("Tab")
        page.keyboard.press("Space")
        page.keyboard.press("Escape")
        check("Keyboard: Space toggles, Escape closes and returns focus",
              button.get_attribute("aria-expanded") == "false"
              and page.evaluate("document.activeElement.getAttribute('aria-expanded')") == "false")
        page.wait_for_url(re.compile("group=Burgers"))

        check("No uncaught page errors", not console_errors, "; ".join(console_errors))

        # Responsive layouts
        for name, width, height in [("small-laptop-1280", 1280, 800), ("tablet-820", 820, 1100), ("mobile-390", 390, 844)]:
            small = browser.new_page(viewport={"width": width, "height": height})
            small.goto(app)
            wait_for_dashboard(small)
            overflow = small.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"{name}: no horizontal page overflow", overflow <= 0, f"{overflow}px")
            offscreen = []
            for label in ["Outlet", "Menu group", "Order type", "Channel / settlement"]:
                small.get_by_role("button", name=label).click()
                box = small.locator(".select-panel").bounding_box()
                if box["x"] < 0 or box["x"] + box["width"] > width:
                    offscreen.append(f"{label}: x={box['x']:.0f} w={box['width']:.0f}")
                small.keyboard.press("Escape")
            check(f"{name}: dropdown panels stay within the viewport", not offscreen, "; ".join(offscreen))
            if shots:
                small.screenshot(path=str(shots / f"{name}.png"), full_page=True)
            small.close()

        browser.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
