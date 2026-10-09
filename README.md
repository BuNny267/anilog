# AniLog — Personal Anime Tracker

A glassmorphic, mobile-first anime tracking app built with Flask + SQLite + AniList GraphQL.

## Features
- **Discover** — Trending, airing, top-rated, seasonal, movies, new releases
- **Search** — Debounced live search with no page reloads
- **My List** — Status tabs, grid/list views, filters, sorting
- **Anime Details** — Synopsis, info grid, cast with JP/EN voice actors, franchise timeline
- **Schedule** — Airing schedule for the next 7 days
- **Stats** — Donut charts, genre breakdown, episode tracking
- **Custom Lists** — Create named lists like "Favorites"
- **Recommendations** — Genre-based suggestions
- **Rewatch Tracking** — Track how many times you've rewatched
- **Offline Support** — Service worker caching
- **No Page Reloads** — All actions update the DOM in-place

## Quick Start

```bash
cd anime-tracker
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Tech Stack
- Flask (Python web framework)
- SQLite3 (database)
- AniList GraphQL API (anime data)
- Vanilla JavaScript (no frameworks)
- CSS custom properties (theming)

## Data Source
All anime data is powered by [AniList](https://anilist.co).
Not affiliated with AniList or MyAnimeList.