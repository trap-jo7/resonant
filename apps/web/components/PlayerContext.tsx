"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { getAudio, Track } from "@/lib/api";

type Range = { start: number; end: number } | null;
type Ctx = {
  audio: HTMLAudioElement | null; track: Track | null; playing: boolean; time: number; duration: number;
  range: Range; loop: boolean; setLoop: (b: boolean) => void; setRange: (r: Range) => void;
  loadTrack: (t: Track) => Promise<void>; toggle: () => void; seek: (s: number) => void;
  playRange: (t: Track, start: number, end: number) => Promise<void>; playFull: (t: Track) => Promise<void>;
};
const PlayerCtx = createContext<Ctx | null>(null);
export const usePlayer = () => { const c = useContext(PlayerCtx); if (!c) throw new Error("PlayerProvider missing"); return c; };

/** One playback controller for the whole app: a single <audio> element, so starting anything stops the previous audio. */
export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [range, setRange] = useState<Range>(null);
  const [loop, setLoop] = useState(false);
  const loadedId = useRef<string | null>(null);
  const rangeRef = useRef<Range>(null); rangeRef.current = range;
  const loopRef = useRef(false); loopRef.current = loop;

  useEffect(() => {
    if (!audio) return;
    const on = (e: string, f: () => void) => { audio.addEventListener(e, f); return () => audio.removeEventListener(e, f); };
    const offs = [
      on("play", () => setPlaying(true)), on("pause", () => setPlaying(false)), on("ended", () => setPlaying(false)),
      on("loadedmetadata", () => setDuration(audio.duration || 0)),
      on("timeupdate", () => setTime(audio.currentTime)),
      on("error", async () => {            // signed URLs expire; refresh once and resume where we were
        if (!loadedId.current) return;
        const at = audio.currentTime, was = !audio.paused;
        try { const { url } = await getAudio(loadedId.current); audio.src = url; audio.currentTime = at; if (was) await audio.play(); } catch {}
      }),
    ];
    let raf = 0;
    const tick = () => {                   // precise stop/loop at the end of a selected range
      const r = rangeRef.current;
      if (r && !audio.paused && audio.currentTime >= r.end) {
        if (loopRef.current) audio.currentTime = r.start; else { audio.pause(); audio.currentTime = r.end; }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { offs.forEach((f) => f()); cancelAnimationFrame(raf); };
  }, [audio]);

  const loadTrack = useCallback(async (t: Track) => {
    if (!audio || !t.availability.playback) return;
    setTrack(t);
    if (loadedId.current === t.id) return;
    audio.pause();
    const { url } = await getAudio(t.id);
    loadedId.current = t.id; audio.src = url; audio.load(); setTime(0);
  }, [audio]);

  const value = useMemo<Ctx>(() => ({
    audio, track, playing, time, duration, range, loop, setLoop, setRange, loadTrack,
    toggle: () => { if (!audio) return; audio.paused ? audio.play().catch(() => {}) : audio.pause(); },
    seek: (s) => { if (audio) audio.currentTime = s; },
    playRange: async (t, start, end) => {
      if (!audio) return; await loadTrack(t); setRange({ start, end });
      audio.currentTime = start; await audio.play().catch(() => {});
    },
    playFull: async (t) => { if (!audio) return; await loadTrack(t); setRange(null); audio.currentTime = 0; await audio.play().catch(() => {}); },
  }), [audio, track, playing, time, duration, range, loop, loadTrack]);

  return (<PlayerCtx.Provider value={value}>{children}<audio ref={setAudio} preload="metadata" /></PlayerCtx.Provider>);
}
