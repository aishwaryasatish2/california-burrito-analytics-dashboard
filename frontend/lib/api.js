// The only module that talks to the backend.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function getJson(path, signal) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { signal });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(`Could not reach the API at ${API_URL}.`);
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch {
      // Non-JSON error body; the status code is enough.
    }
    throw new Error(`The API returned ${response.status}${detail ? `: ${detail}` : "."}`);
  }
  return response.json();
}

export function fetchFilterOptions(signal) {
  return getJson("/api/filters", signal);
}

export function fetchDashboard(queryString, signal) {
  return getJson(`/api/dashboard${queryString ? `?${queryString}` : ""}`, signal);
}
