"use client";
import { AnimatePresence, motion } from "motion/react";
import { fmt } from "@/lib/api";
import Artwork from "./Artwork";
import Equalizer from "./Equalizer";
import { usePlayer } from "./PlayerContext";

export default function BottomPlayer() {
  const p = usePlayer();
  return (
    <AnimatePresence>
      {p.track && (
        <motion.div role="region" aria-label="Player" initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 260, damping: 28 }} className="fixed inset-x-3 bottom-3 z-20 md:left-28">
          <div className="card mx-auto flex max-w-4xl items-center gap-3 p-3 shadow-2xl shadow-black/50">
            <Artwork track={p.track} size={44} glow={p.playing} />
            <button className="btn btn-accent !h-11 !w-11 !min-h-0 !p-0" onClick={p.toggle} aria-label={p.playing ? "Pause" : "Play"}>{p.playing ? "❚❚" : "▶"}</button>
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 truncate text-sm font-medium">{p.track.title} <span className="font-normal text-dim">· {p.track.artist}</span> <Equalizer active={p.playing} /></p>
              <input type="range" className="mt-1 w-full accent-[#8BE0C1]" aria-label="Seek" min={0} max={p.duration || 0} step={0.1}
                     value={Math.min(p.time, p.duration || 0)} onChange={(e) => p.seek(parseFloat(e.target.value))} />
            </div>
            <span className="tnum hidden text-xs text-dim sm:block">{fmt(p.time)} / {fmt(p.duration)}</span>
          </div>
        </motion.div>)}
    </AnimatePresence>
  );
}
