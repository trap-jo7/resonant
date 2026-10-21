"use client";
import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin, { Region } from "wavesurfer.js/dist/plugins/regions.esm.js";
import { usePlayer } from "./PlayerContext";

type Props = { peaks: number[]; duration: number; selectable: boolean; start: number; end: number; onRegion: (s: number, e: number) => void };

/** Draws the real waveform peaks computed by the worker, bound to the shared player element. */
export default function Waveform({ peaks, duration, selectable, start, end, onRegion }: Props) {
  const { audio } = usePlayer();
  const box = useRef<HTMLDivElement>(null);
  const region = useRef<Region | null>(null);
  const regions = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const cb = useRef(onRegion); cb.current = onRegion;

  useEffect(() => {
    if (!audio || !box.current) return;
    const rp = RegionsPlugin.create(); regions.current = rp;
    const ws = WaveSurfer.create({
      container: box.current, media: audio, peaks: [peaks], duration, height: 96, barWidth: 2, barGap: 1, barRadius: 2,
      waveColor: "#4a535e", progressColor: "#8BE0C1", cursorColor: "#F3F4F6", plugins: [rp],
    });
    rp.on("region-updated", (r) => cb.current(+r.start.toFixed(2), +r.end.toFixed(2)));
    return () => { region.current = null; ws.destroy(); };
  }, [audio, peaks, duration]);

  useEffect(() => {
    const rp = regions.current; if (!rp) return;
    if (!selectable) { region.current?.remove(); region.current = null; return; }
    if (!region.current) {
      region.current = rp.addRegion({ start, end, drag: true, resize: true, minLength: 5, maxLength: 60, color: "rgba(139,224,193,0.22)" });
    } else if (Math.abs(region.current.start - start) > 0.02 || Math.abs(region.current.end - end) > 0.02) {
      region.current.setOptions({ start, end });
    }
  }, [selectable, start, end, peaks, duration]);

  return <div ref={box} className="w-full" role="img" aria-label="Audio waveform. Use the start and end fields to adjust the selection without dragging." />;
}
