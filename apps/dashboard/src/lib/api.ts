// Server-side and browser access to the DebugAssist API (packages/api, port 8400).
export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8400";
export const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8400";

// Headers for the API's POSTs: when the API requires DA_API_TOKEN, the dashboard sends the same value.
export function postHeaders(): Record<string, string> {
  const token = process.env.NEXT_PUBLIC_DA_API_TOKEN;
  return { "content-type": "application/json", ...(token ? { "x-debugassist-token": token } : {}) };
}

export async function api<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // the API is down: pages render an explanation instead of crashing
  }
}
