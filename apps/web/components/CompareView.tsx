"use client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { ApiError, compareJobs, CompareSeed, createJob, fmt, Job, Mode, Track, waitForJob } from "@/lib/api";
import Artwork from "./Artwork";
import { usePlayer } from "./PlayerContext";
import ScoreRing from "./ScoreRing";
import Segmented from "./Segmented";
import TimeField from "./TimeField";
import TrackPicker from "./TrackPicker";

type Slot = { track: Track | null; start: number; end: number };
type Result = Awaited<ReturnType<typeof compareJobs>>;
const EMPTY: Slot = { track: null, start: 0, end: 20 };
const LABELS: Record<string, string> = { embedding: "Audio embedding", harmonic: "Harmonic profile", rhythm: "Rhythm", timbre: "Energy / timbre" };

function fill(t: Track, start?: number, end?: number): Slot {
  if (start != null && end != null) return { track: t, start, end };
  const d = t.duration_s ?? 60, s = Math.max(0, Math.min(d / 2 - 10, d - 20));   // 20 s from the middle of the song
  return { track: t, start: +s.toFixed(1), end: +Math.min(d, s + 20).toFixed(1) };
}
// Rough, arbitrary wording thresholds on an uncalibrated score. Shown with that caveat.
const verdict = (s: number) => (s >= 0.75 ? "Very similar" : s >= 0.6 ? "Similar" : s >= 0.45 ? "Some overlap" : "Quite different");

function SlotCard({ name, slot, set, status }: { name: string; slot: Slot; set: (s: Slot) => void; status?: string }) {
  const p = usePlayer();
  const t = slot.track;
  return (
    <div className="card grid content-start gap-4 p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><span className="grid h-6 w-6 place-items-center rounded-full bg-accent text-xs text-bg">{name}</span> Track {name}</h2>
        {status && <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-dim" role="status">{status}</span>}
      </div>
      <AnimatePresence mode="wait" initial={false}>
        {!t ? (
          <motion.div key="pick" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <TrackPicker label={`Choose track ${name}`} compact onSelect={(x) => set(fill(x))} />
          </motion.div>
        ) : (
          <motion.div key={t.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="grid gap-4">
            <div className="flex items-center gap-4"><Artwork track={t} size={72} glow />
              <div className="min-w-0"><p className="truncate text-lg font-semibold">{t.title}</p><p className="truncate text-sm text-dim">{t.artist}</p>
                <p className="tnum text-xs text-dim">{t.duration_s ? fmt(t.duration_s) : ""}</p></div></div>
            {t.availability.audio_analysis ? (<>
              <div className="flex flex-wrap items-end gap-3">
                <TimeField label="Start" value={slot.start} max={t.duration_s ?? 600} onChange={(v) => set({ ...slot, start: v })} />
                <TimeField label="End" value={slot.end} max={t.duration_s ?? 600} onChange={(v) => set({ ...slot, end: v })} />
                <span className="tnum pb-2.5 text-xs text-dim">{(slot.end - slot.start).toFixed(1)} s</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn" disabled={!t.availability.playback} onClick={() => p.playRange(t, slot.start, slot.end)}>▶ Preview selection</button>
                <button className="btn" onClick={() => set(EMPTY)}>Change song</button></div>
            </>) : (
              <div className="grid gap-3 rounded-xl bg-white/6 p-4 text-sm">
                <p>{t.availability.message}</p>
                <div className="flex gap-2"><button className="btn" onClick={() => set(EMPTY)}>Pick another song</button></div>
              </div>)}
          </motion.div>)}
      </AnimatePresence>
    </div>
  );
}

export default function CompareView({ seed, onSeedUsed }: { seed: CompareSeed | null; onSeedUsed: () => void }) {
  const [a, setA] = useState<Slot>(EMPTY);
  const [b, setB] = useState<Slot>(EMPTY);
  const [mode, setMode] = useState<Mode>("balanced");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [st, setSt] = useState<{ a?: string; b?: string }>({});

  useEffect(() => {
    if (!seed) return;
    if (seed.a) setA(fill(seed.a.track, seed.a.start, seed.a.end));
    if (seed.b) setB(fill(seed.b.track, seed.b.start, seed.b.end));
    setRes(null); setErr(null); onSeedUsed();
  }, [seed, onSeedUsed]);

  const ready = !!a.track?.availability.audio_analysis && !!b.track?.availability.audio_analysis;

  async function run() {
    if (!ready) return;
    setBusy(true); setErr(null); setRes(null); setSt({});
    try {
      const jobs: Job[] = await Promise.all([a, b].map((s) => createJob({ track_id: s.track!.id, start_s: s.start, end_s: s.end })));
      await Promise.all(jobs.map((j, i) => waitForJob(j.id, (x) => setSt((o) => ({ ...o, [i ? "b" : "a"]: x })))));
      setRes(await compareJobs(jobs[0].id, jobs[1].id, mode));
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Comparison failed. Try again."); } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-6">
      <p className="text-sm text-dim">Search any song in the catalog (or upload your own file), pick the moment in each, and compare them with the same features and scoring as catalog search. Nothing is added to the catalog.</p>
      <div className="grid items-start gap-4 lg:grid-cols-[1fr_auto_1fr]">
        <SlotCard name="A" slot={a} set={(s) => { setA(s); setRes(null); }} status={st.a} />
        <button className="btn mx-auto self-center !h-11 !w-11 !min-h-0 !p-0" aria-label="Swap tracks A and B" onClick={() => { setA(b); setB(a); setRes(null); }}>⇄</button>
        <SlotCard name="B" slot={b} set={(s) => { setB(s); setRes(null); }} status={st.b} />
      </div>
      <div className="flex flex-wrap items-center justify-center gap-4">
        <Segmented id="cmpmode" label="Match on" value={mode} onChange={(m) => { setMode(m); setRes(null); }}
                   options={[{ value: "balanced", label: "Balanced" }, { value: "vibe", label: "Vibe" }, { value: "harmony", label: "Harmony" }]} />
        <button className="btn btn-accent !px-8 !py-3" disabled={!ready || busy} onClick={run}>{busy ? "Comparing…" : "Compare"}</button>
      </div>
      {!ready && (a.track || b.track) && <p className="text-center text-xs text-dim">Pick an analyzable song for both slots to compare. Songs shown as “Metadata only” can’t be analyzed without permitted audio.</p>}
      <div aria-live="polite">
        {err && <p role="alert" className="text-center text-sm text-[#ff9b9b]">{err}</p>}
        <AnimatePresence>
          {res && (
            <motion.div initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                        className="card mx-auto grid max-w-2xl gap-5 p-6 sm:grid-cols-[auto_1fr] sm:items-center">
              <div className="grid justify-items-center gap-2"><ScoreRing value={res.score} size={120} stroke={9} label="Comparison score" />
                <p className="text-lg font-semibold">{verdict(res.score)}</p>
                {res.confidence === "low" && <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-dim">Low confidence</span>}</div>
              <div className="grid gap-3 text-xs">
                {Object.entries(res.components).map(([k, c], i) => (
                  <div key={k} className="grid gap-1"><div className="flex justify-between"><span>{LABELS[k] ?? k}</span>
                    <span className="tnum text-dim">{c.score.toFixed(2)} · feature confidence {c.confidence.toFixed(2)}</span></div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><motion.div className="h-full rounded-full bg-gradient-to-r from-[#8BE0C1] to-[#6fd0ff]"
                      initial={{ width: 0 }} animate={{ width: `${c.score * 100}%` }} transition={{ delay: 0.15 + i * 0.08, duration: 0.6 }} /></div></div>))}
                {res.harmonic_shift_semitones !== 0 && <p className="text-dim">Best harmonic alignment needs a shift of {res.harmonic_shift_semitones > 0 ? "+" : ""}{res.harmonic_shift_semitones} semitones.</p>}
                <p className="text-dim">Experimental, uncalibrated score; the wording above uses rough cut-offs. {res.note}</p>
              </div>
            </motion.div>)}
        </AnimatePresence>
      </div>
    </div>
  );
}
