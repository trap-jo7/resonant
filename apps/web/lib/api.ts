export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Availability = { audio_analysis: boolean; playback: boolean; message?: string | null };
export type Track = {
  id: string; title: string; artist: string; album?: string | null; duration_s?: number | null; artwork_url?: string | null;
  source: string; source_url?: string | null; license?: string | null; attribution?: string | null;
  is_private_upload: boolean; availability: Availability;
};
export type Job = { id: string; status: "queued" | "processing" | "ready" | "failed" | "cancelled"; error?: string | null; retryable: boolean };
export type Component = { score: number; confidence: number };
export type Match = {
  result_id: number; track: Track; start_s: number; end_s: number; score: number; confidence: "ok" | "low";
  coverage?: number | null; components: Record<string, Component>; explanations: string[];
};
export type SearchOut = {
  search_id: string; mode: string; weights: Record<string, number>; weights_note: string;
  analysis_versions: Record<string, unknown>; quality: "ok" | "weak" | "empty"; latency_ms: number; results: Match[];
};
export type Mode = "balanced" | "vibe" | "harmony";

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...init });
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const searchCatalog = (q: string, signal?: AbortSignal) => req<Track[]>(`/api/catalog/search?q=${encodeURIComponent(q)}`, { signal });
export const getTrack = (id: string) => req<Track>(`/api/tracks/${id}`);
export const getAudio = (id: string) => req<{ url: string; expires_in: number }>(`/api/tracks/${id}/audio`);
export const getWaveform = (id: string) => req<{ peaks: number[]; duration_s: number }>(`/api/tracks/${id}/waveform`);
export function upload(file: File, authorized: boolean, signal?: AbortSignal) {
  const f = new FormData(); f.append("file", file); f.append("authorized", String(authorized));
  return req<{ track_id: string; job_id: string; retention_hours: number }>("/api/uploads", { method: "POST", body: f, signal });
}
export const deleteUpload = (id: string) => req<void>(`/api/uploads/${id}`, { method: "DELETE" });
export const createJob = (b: { track_id: string; start_s?: number; end_s?: number; whole_song?: boolean }) => req<Job>("/api/analysis/jobs", json(b));
export const getJob = (id: string, signal?: AbortSignal) => req<Job>(`/api/analysis/jobs/${id}`, { signal });
export const cancelJob = (id: string) => req<Job>(`/api/analysis/jobs/${id}/cancel`, { method: "POST" });
export const similarity = (job_id: string, mode: Mode) => req<SearchOut>("/api/searches", json({ job_id, mode }));
export const compareJobs = (job_a: string, job_b: string, mode: Mode) =>
  req<{ score: number; confidence: string; components: Record<string, Component>; harmonic_shift_semitones: number; note: string }>("/api/compare", json({ job_a, job_b, mode }));
export const sendFeedback = (result_id: number, label: "good" | "poor") => req<void>("/api/feedback", json({ result_id, label }));
export const saveItem = (track_id: string, start_s?: number, end_s?: number) => req<{ id: number }>("/api/saved", json({ track_id, start_s, end_s }));

const sleep = (ms: number, signal?: AbortSignal) => new Promise<void>((res, rej) => {
  const t = setTimeout(res, ms); signal?.addEventListener("abort", () => { clearTimeout(t); rej(new DOMException("Aborted", "AbortError")); });
});

/** Poll a real job until it reaches a terminal state. `onStatus` reports actual queued/processing states. */
export async function waitForJob(id: string, onStatus: (s: Job["status"]) => void, signal?: AbortSignal): Promise<Job> {
  for (;;) {
    const j = await getJob(id, signal); onStatus(j.status);
    if (j.status === "ready") return j;
    if (j.status === "failed" || j.status === "cancelled") throw new ApiError(422, j.error ?? "Analysis was cancelled.");
    await sleep(700, signal);
  }
}
export async function waitForWaveform(id: string, signal?: AbortSignal) {
  for (let i = 0; i < 120; i++) {
    try { return await getWaveform(id); } catch (e) { if (!(e instanceof ApiError && e.status === 409)) throw e; }
    await sleep(1000, signal);
  }
  throw new ApiError(504, "Preparing the waveform is taking longer than expected.");
}

export const fmt = (s: number) => { const t = Math.max(0, s); const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(1).padStart(4, "0")}`; };
export function parseTime(text: string): number | null {
  const m = text.trim().match(/^(?:(\d+):)?(\d{1,2}(?:\.\d+)?)$/); if (!m) return null;
  return (m[1] ? parseInt(m[1]) * 60 : 0) + parseFloat(m[2]);
}

export type CompareSide = { track: Track; start?: number; end?: number };
export type CompareSeed = { a?: CompareSide; b?: CompareSide };
