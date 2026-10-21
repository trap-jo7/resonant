"use client";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useId, useRef, useState } from "react";
import { ApiError, getTrack, searchCatalog, Track, upload } from "@/lib/api";
import Artwork from "./Artwork";

export default function TrackPicker({ label, onSelect, compact = false, autoUploadOpen = false }:
  { label: string; onSelect: (t: Track) => void; compact?: boolean; autoUploadOpen?: boolean }) {
  const [q, setQ] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(!compact || autoUploadOpen);
  const file = useRef<HTMLInputElement>(null);
  const id = useId();
  const { data, isFetching, error, refetch } = useQuery({ queryKey: ["catalog", q], queryFn: ({ signal }) => searchCatalog(q, signal) });

  async function onFile(f: File | undefined) {
    if (!f) return;
    setErr(null); setBusy(true);
    try { const up = await upload(f, authorized); onSelect(await getTrack(up.track_id)); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Upload failed. Please try again."); }
    finally { setBusy(false); if (file.current) file.current.value = ""; }
  }

  return (
    <section aria-label={label} className="grid gap-4">
      <div className="relative">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-dim" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input type="search" aria-label="Search the catalog" placeholder="Search a song or artist…" className="field w-full !rounded-2xl !py-3.5 !pl-12 !text-base"
               value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div aria-live="polite" className="grid gap-2">
        {error && (
          <div role="alert" className="card flex flex-wrap items-center gap-3 p-4 text-sm">
            <span className="text-[#ff9b9b]">Can’t reach the Resonant backend. Start Docker Desktop, then run <code className="rounded bg-white/10 px-1.5 py-0.5">docker compose up -d</code> in the project folder.</span>
            <button className="btn" onClick={() => refetch()}>Retry</button>
          </div>)}
        {isFetching && !data && [0, 1, 2].map((i) => <div key={i} className="shimmer h-[68px] rounded-2xl" aria-hidden="true" />)}
        {data && data.length === 0 && !isFetching && (
          <p className="card p-4 text-sm text-dim">No tracks found. Try another search, or upload audio you’re authorized to use.</p>)}
        {data && data.length > 0 && <h2 className="px-1 text-xs font-medium uppercase tracking-wider text-dim">{q ? "Results" : "Indexed examples"}</h2>}
        <ul className="grid gap-2">
          {data?.map((t, i) => (
            <motion.li key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.04 }}>
              <button className="card card-hover flex w-full items-center gap-3 p-3 text-left" onClick={() => onSelect(t)}>
                <Artwork track={t} size={48} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{t.title}</span>
                  <span className="block truncate text-xs text-dim">{t.artist}{t.license ? ` · ${t.license}` : ""}</span>
                </span>
                {t.availability.audio_analysis
                  ? <span className="rounded-full bg-accent/15 px-2.5 py-1 text-xs text-accent">Analyzable</span>
                  : <span className="rounded-full bg-white/8 px-2.5 py-1 text-xs text-dim">Metadata only</span>}
              </button>
            </motion.li>))}
        </ul>
      </div>

      {compact && !showUpload && (
        <button className="btn justify-self-start" onClick={() => setShowUpload(true)}>Upload your own file instead</button>)}
      {showUpload && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card flex flex-wrap items-center gap-3 p-4">
          <input id={`${id}-auth`} type="checkbox" className="h-4 w-4 accent-[#8BE0C1]" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} />
          <label htmlFor={`${id}-auth`} className="text-sm">I’m authorized to use this audio</label>
          <button className="btn btn-accent" disabled={!authorized || busy} onClick={() => file.current?.click()}>{busy ? "Uploading…" : "Upload audio"}</button>
          <input ref={file} type="file" hidden accept=".mp3,.wav,.flac,.m4a,audio/*" onChange={(e) => onFile(e.target.files?.[0])} aria-label="Audio file" />
          <p className="w-full text-xs text-dim">MP3, WAV, FLAC or M4A, up to 50 MB and 10 minutes. Private to you; deleted automatically after 24 hours.</p>
          {err && <p role="alert" className="w-full text-sm text-[#ff9b9b]">{err}</p>}
        </motion.div>)}
    </section>
  );
}
