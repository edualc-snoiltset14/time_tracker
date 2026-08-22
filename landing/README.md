# Top Streams landing page

A self-contained landing page listing the five most-streamed songs of every
year since 2010. Pick a year and the chart re-renders with cover artwork,
approximate stream totals, and a relative-size bar per track.

## Running it

No build step and no dependencies — open the file directly:

```sh
open landing/index.html        # macOS
xdg-open landing/index.html    # Linux
```

Or serve the folder if you prefer a real origin:

```sh
npx http-server landing -o
```

## Editing the data

All the chart data lives in the `CHARTS` object inside `index.html`, keyed by
year. Each entry is:

```js
{ title: "Blinding Lights", artist: "The Weeknd", s: 4.9 }
```

`s` is the approximate cumulative stream count in billions, and entries are
listed in rank order. To add a year, add a key with five entries — the year
buttons are generated from the object's keys, so nothing else needs changing.

## Artwork

Covers are generated at render time: a hash of the artist and title picks a
stable gradient, disc placement, and monogram, so a given track always looks
the same. No copyrighted images are bundled.

To use a real image for a track, add a `cover` field and it will be used
instead of the generated artwork:

```js
{ title: "Blinding Lights", artist: "The Weeknd", s: 4.9, cover: "https://…/cover.jpg" }
```

## Caveats

The stream counts are a hand-curated static snapshot, rounded, and songs are
grouped by release year rather than by chart week. They are not live figures
and will drift from what the streaming platforms currently report.
