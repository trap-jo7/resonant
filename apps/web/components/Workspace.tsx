"use client";
import { AnimatePresence, motion } from "motion/react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError, cancelJob, CompareSeed, createJob, deleteUpload, fmt, Match, Mode, SearchOut, similarity, Track, waitForJob, waitForWaveform,
} from "@/lib/api";
import Artwork from "./Artwork";
import { usePlayer } from "./PlayerContext";
import Results from "./Results";
import Segmented from "./Segmented";
import Steps from "./Steps";
import TimeField from "./TimeField";
import TrackPicker from "./TrackPicker";

const Waveform = dynamic(() => import("./Waveform"), { ssr: false, loading: () => <div className="shimmer h-24 rounded-xl" aria-label="Loading waveform" role="status" /> });
const MIN = 5, MAX = 60;
const STEP: Record<string, number> = { queued: 0, processing: 1, searching: 2 };

export default function Workspace({ onCompare }: { onCompare: (seed: CompareSeed) => void }) {
  const player = usePlayer();
  const [track, setTrack] = useState<Track | null>(null);
  const [wave, setWave] = useState<{ peaks: number[]; duration: number } | null>(null);
  const [waveErr, setWaveErr] = useState<string | null>(null);
  const [whole, setWhole] = useState(false);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(20);
  const [mode, setMode] = useState<Mode>("balanced");
  const [phase, setPhase] = useState<string | null>(null);
  const [error, setError] = useState<{ msg: string; retry: boolean } | null>(null);
  const [out, setOut] = useState<SearchOut | null>(null);
  const ctrl = useRef<AbortController | null>(null);
  const jobId = useRef<string | null>(null);
  const duration = wave?.duration ?? track?.duration_s ?? 0;

  const select = useCallback(async (t: Track) => {
    ctrl.current?.abort();
    setTrack(t); setWave(null); setWaveErr(null); setOut(null); setError(null); setPhase(null); setWhole(false);
    if (!t.availability.playback) return;
    const c = new AbortController(); ctrl.current = c;
    try {
      await player.loadTrack(t);
      const w = await waitForWaveform(t.id, c.signal);
      setWave({ peaks: w.peaks, duration: w.duration_s });
      const s = Math.max(0, Math.min(w.duration_s / 2 - 10, w.duration_s - 20));   // start from the middle, not the intro
      setStart(+s.toFixed(1)); setEnd(+Math.min(w.duration_s, s + 20).toFixed(1));
    } catch (e) { if ((e as Error).name !== "AbortError") setWaveErr(e instanceof ApiError ? e.message : "Couldn’t load this audio."); }
  }, [player]);

  useEffect(() => {      // Space toggles playback unless typing in a field
    const h = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.code === "Space" && !/INPUT|TEXTAREA|SELECT|BUTTON/.test(el.tagName)) { e.preventDefault(); player.toggle(); }
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [player]);

  useEffect(() => { player.setRange(!whole && wave ? { start, end } : null); }, [whole, wave, start, end]); // eslint-disable-line react-hooks/exhaustive-deps

  const len = end - start;
  const selErr = whole ? null : len < MIN ? `Select at least ${MIN} seconds.` : len > MAX ? `Select at most ${MAX} seconds, or use whole song.` : null;

  async function find() {
    if (!track) return;
    ctrl.current?.abort(); const c = new AbortController(); ctrl.current = c;
    setError(null); setOut(null); setPhase("queued");
    try {
      const job = await createJob(whole ? { track_id: track.id, whole_song: true } : { track_id: track.id, start_s: start, end_s: end });
      jobId.current = job.id;
      await waitForJob(job.id, (s) => setPhase(s === "ready" ? "searching" : s), c.signal);
      setPhase("searching");
      setOut(await similarity(job.id, mode));
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError({ msg: e instanceof ApiError ? e.message : "Something went wrong.", retry: true });
    } finally { if (!c.signal.aborted) setPhase(null); }
  }
  function cancel() { ctrl.current?.abort(); if (jobId.current) cancelJob(jobId.current).catch(() => {}); setPhase(null); }
  async function removeUpload() {
    if (!track) return;
    await deleteUpload(track.id).catch(() => {});
    if (player.track?.id === track.id) player.audio?.pause();
    setTrack(null); setWave(null); setOut(null);
  }
  const mine = track ? { track, start: whole ? undefined : start, end: whole ? undefined : end } : undefined;

  return (
    <div className="grid gap-8">
      <TrackPicker label="Find a track" onSelect={select} />
      <AnimatePresence mode="popLayout">
        {track && (
          <motion.section key={track.id} aria-label="Selected track" layout initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }} className="card grid gap-5 p-5 sm:p-6">
            <div className="flex items-center gap-5">
              <Artwork track={track} size={96} glow />
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wider text-accent">Selected</p>
                <h2 className="truncate text-2xl font-semibold">{track.title}</h2>
                <p className="truncate text-sm text-dim">{track.artist}</p>
                <p className="tnum text-xs text-dim">{duration ? fmt(duration) : ""}{track.license ? ` · ${track.license}` : ""}</p>
              </div>
              <div className="ml-auto flex flex-col gap-2 sm:flex-row">
                {track.availability.audio_analysis && <button className="btn" onClick={() => onCompare({ a: mine })}>Compare with another song</button>}
                {track.is_private_upload && <button className="btn" onClick={removeUpload}>Delete now</button>}
              </div>
            </div>

            {!track.availability.audio_analysis && <p role="status" className="rounded-xl bg-white/6 p-4 text-sm">{track.availability.message}</p>}
            {track.availability.audio_analysis && !wave && !waveErr && <div role="status" className="grid gap-2 text-sm text-dim">Preparing audio and waveform…<div className="shimmer h-24 rounded-xl" aria-hidden="true" /></div>}
            {waveErr && <p role="alert" className="text-sm text-[#ff9b9b]">{waveErr}</p>}

            {wave && track.availability.audio_analysis && (<>
              <div className="rounded-xl bg-black/25 p-3">
                <Waveform peaks={wave.peaks} duration={wave.duration} selectable={!whole} start={start} end={end} onRegion={(s, e) => { setStart(s); setEnd(e); }} />
              </div>
              <div className="flex flex-wrap items-end gap-4">
                <Segmented id="scope" label="Search scope" value={whole ? "whole" : "section"} onChange={(v) => setWhole(v === "whole")}
                           options={[{ value: "whole", label: "Whole song" }, { value: "section", label: "Select a section" }]} />
                <AnimatePresence initial={false}>
                  {!whole && (
                    <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} className="flex flex-wrap items-end gap-3">
                      <TimeField label="Start" value={start} max={duration} onChange={setStart} />
                      <TimeField label="End" value={end} max={duration} onChange={setEnd} />
                      <span className="tnum pb-2.5 text-xs text-dim">{len.toFixed(1)} s · 10–30 s works best</span>
                    </motion.div>)}
                </AnimatePresence>
              </div>
              <p id="time-help" className="text-xs text-dim">Type a time like 1:23.5, or press ↑/↓ to nudge by 0.5 s (Shift for 5 s). Space plays or pauses.</p>
              {selErr && <p role="alert" className="text-sm text-[#ff9b9b]">{selErr}</p>}
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn" onClick={player.toggle}>{player.playing ? "❚❚ Pause" : "▶ Play"}</button>
                <button className="btn" disabled={whole} onClick={() => player.playRange(track, start, end)}>Replay selection</button>
                <button className="btn" aria-pressed={player.loop} disabled={whole} onClick={() => player.setLoop(!player.loop)}>Loop selection</button>
                <div className="ml-auto flex flex-wrap items-center gap-3">
                  <Segmented id="mode" label="Match on" value={mode} onChange={setMode}
                             options={[{ value: "balanced", label: "Balanced" }, { value: "vibe", label: "Vibe" }, { value: "harmony", label: "Harmony" }]} />
                  {phase ? <button className="btn" onClick={cancel}>Cancel</button>
                    : <button className="btn btn-accent !px-6" disabled={!!selErr} onClick={find}>Find similar</button>}
                </div>
              </div>
            </>)}
            <AnimatePresence>
              {phase && <motion.div key="steps" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}><Steps active={STEP[phase] ?? 0} /></motion.div>}
            </AnimatePresence>
            {error && (<div role="alert" className="flex items-center gap-3 text-sm text-[#ff9b9b]">{error.msg}
              {error.retry && <button className="btn" onClick={find}>Try again</button>}</div>)}
          </motion.section>
        )}
      </AnimatePresence>
      {out && mine && <Results out={out} onCompare={(m: Match) => onCompare({ a: mine, b: { track: m.track, start: m.start_s, end: m.end_s } })} />}
    </div>
  );
}
