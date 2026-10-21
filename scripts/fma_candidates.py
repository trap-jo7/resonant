"""List FMA tracks worth checking for the demo catalog.

    python scripts/fma_candidates.py path/to/fma_metadata/tracks.csv > data/fma_candidates.csv

Filters by license text and a minimum duration, then spreads picks across top-level genres.
This only *suggests* tracks. You must still open each track's FMA page, confirm the artist-selected license
allows analysis, playback and storage for your use, obtain a FULL-LENGTH file, and record the evidence in the manifest.
fma_small/medium/large contain 30 s clips; they are fine for pipeline development but not for arbitrary trimming demos.
"""
import sys
import pandas as pd

df = pd.read_csv(sys.argv[1], index_col=0, header=[0, 1])
t = pd.DataFrame({
    "track_id": df.index, "title": df[("track", "title")], "artist": df[("artist", "name")],
    "album": df[("album", "title")], "genre": df[("track", "genre_top")],
    "license": df[("track", "license")], "duration_s": df[("track", "duration")],
    "page": df[("track", "url")] if ("track", "url") in df.columns else "",
})
t = t[t["license"].fillna("").str.contains("Creative Commons", case=False) & (t["duration_s"] >= 90) & (t["duration_s"] <= 420)]
t = t.dropna(subset=["genre"])
picked = t.groupby("genre", group_keys=False).apply(lambda g: g.sample(min(len(g), 6), random_state=7))
picked.to_csv(sys.stdout, index=False)
