"use client";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { fmt, Match, saveItem, SearchOut, sendFeedback } from "@/lib/api";
import Artwork from "./Artwork";
import Equalizer from "./Equalizer";
import { usePlayer } from "./PlayerContext";
import ScoreRing from "./ScoreRing";

const LABELS: Record<string, string> = { embedding: "Audio embedding", harmonic: "Harmonic profile", rhythm: "Rhythm", timbre: "Energy / timbre" };

function Row({ m, out, rank, onCompare }: { m: Match; out: SearchOut; rank: number; onCompare: (m: Match) => void }) {
  const p = usePlayer();
  const [vote, setVote] = useState<"good" | "poor" | null>(null);
  const [saved, setSaved] = useState(false);
  const [open, setOpen] = useState(false);
  const canPlay = m.track.availability.playback;
  const nowPlaying = p.playing && p.track?.id === m.track.id;
  return (
    <motion.li initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(rank, 8) * 0.06, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
               className="card card-hover p-4">
      <div className="flex items-center gap-4">
        <span className="tnum hidden w-5 text-center text-sm text-dim sm:block">{rank + 1}</span>
        <Artwork track={m.track} size={60} glow={nowPlaying} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 truncate text-base font-medium">{m.track.title} {nowPlaying && <Equalizer active />}</p>
          <p className="truncate text-sm text-dim">{m.track.artist}</p>
          <p className="tnum mt-0.5 text-xs text-accent">Matches at {fmt(m.start_s)}–{fmt(m.end_s)}
            {m.coverage != null && <span className="text-dim"> · covers {Math.round(m.coverage * 100)}% of your song</span>}</p>
        </div>
        <div className="flex flex-col items-center gap-1">
          <ScoreRing value={m.score} size={56} />
          {m.confidence === "low" && <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-dim">Low confidence</span>}
        </div>
      </div>
      <ul className="mt-3 list-disc pl-5 text-xs text-dim">{m.explanations.map((e) => <li key={e}>{e}</li>)}</ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button className="btn btn-accent" disabled={!canPlay} onClick={() => p.playRange(m.track, m.start_s, m.end_s)}>▶ Play matching section</button>
        <button className="btn" disabled={!canPlay} onClick={() => p.playFull(m.track)}>Full track</button>
        <button className="btn" onClick={() => onCompare(m)}>Compare with my pick</button>
        <button className="btn" aria-pressed={saved} onClick={async () => { await saveItem(m.track.id, m.start_s, m.end_s).catch(() => {}); setSaved(true); }}>{saved ? "Saved ✓" : "Save"}</button>
        {(["good", "poor"] as const).map((l) => (
          <button key={l} className="btn" aria-pressed={vote === l} onClick={async () => { setVote(l); await sendFeedback(m.result_id, l).catch(() => setVote(null)); }}>
            {l === "good" ? "👍 Good match" : "👎 Poor match"}
          </button>))}
        <button className="btn" aria-expanded={open} onClick={() => setOpen(!open)}>Why this matched</button>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="mt-3 grid gap-3 rounded-xl bg-black/25 p-4 text-xs">
              {Object.entries(m.components).map(([k, c], i) => (
                <div key={k} className="grid gap-1">
                  <div className="flex justify-between"><span>{LABELS[k] ?? k} <span className="text-dim">· weight {(out.weights[k] ?? 0).toFixed(2)}</span></span>
                    <span className="tnum text-dim">score {c.score.toFixed(2)} · feature confidence {c.confidence.toFixed(2)}</span></div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/10"><motion.div className="h-full rounded-full bg-gradient-to-r from-[#8BE0C1] to-[#6fd0ff]"
                    initial={{ width: 0 }} animate={{ width: `${c.score * 100}%` }} transition={{ delay: i * 0.08, duration: 0.6 }} /></div>
                </div>))}
              <p className="text-dim">{out.weights_note} Harmonic similarity compares pitch-class profiles over time; it isn’t a chord or note match.</p>
            </div>
          </motion.div>)}
      </AnimatePresence>
    </motion.li>
  );
}

export default function Results({ out, onCompare }: { out: SearchOut; onCompare: (m: Match) => void }) {
  if (out.quality === "empty") return <p className="card p-5 text-sm text-dim">No close matches in this catalog yet. A bigger catalog or a different section may help.</p>;
  return (
    <section aria-label="Similar songs" className="grid gap-4">
      <div className="flex items-baseline justify-between"><h2 className="text-xl font-semibold">Similar songs</h2>
        <p className="tnum text-xs text-dim">{out.mode} mode · {out.latency_ms} ms</p></div>
      {out.quality === "weak" && <p role="status" className="card p-4 text-sm">Evidence is weak for this selection, so none of these are confident matches. Try a longer section with clearer rhythm or harmony.</p>}
      <ul className="grid gap-3">{out.results.map((m, i) => <Row key={m.result_id} m={m} out={out} rank={i} onCompare={onCompare} />)}</ul>
    </section>
  );
}
