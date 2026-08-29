# Floppy

Self-hosted all-in-one media tracker (movies, TV, anime, books, games, music, podcasts) and
Trakt alternative. Fork of Yamtrack, which it replaced after a trial period.

| | |
|---|---|
| URL | `https://floppy.{SECRET_DOMAIN}` |
| Auth | SSO via Authelia (OpenID Connect), `SOCIALACCOUNT_ONLY: "True"` — no local login |
| Storage | SQLite on Longhorn PVC (`floppy-data-pvc`) |
| Cache/queue | Redis (`floppy-redis`) |

## Metadata API keys

Not configured yet. `TMDB_API`, `TVDB_API_KEY`/`TVDB_PIN`, `MAL_API`, `IGDB_ID`/`IGDB_SECRET`,
`STEAM_API_KEY`, `BGG_API_TOKEN`, `HARDCOVER_API`, `GOOGLE_BOOKS_API_KEY`, `COMICVINE_API`,
`LASTFM_API_KEY` can be added to the `floppy` ConfigMap/Secret as needed per source.

