# Yamtrack

Self-hosted media tracker (movies, TV shows, anime, manga, games, books, comics, board games).

| | |
|---|---|
| URL | `https://yamtrack.{SECRET_DOMAIN}` |
| Auth | SSO via Authelia (OpenID Connect), `SOCIALACCOUNT_ONLY: "True"` — no local login |
| Storage | SQLite on Longhorn PVC (`yamtrack-data-pvc`) |
| Cache/queue | Redis (`yamtrack-redis`) |

## Jellyfin integration

Yamtrack does not pull data from Jellyfin — Jellyfin pushes playback events to Yamtrack via webhook.

### One-time setup

1. Install the **Webhook** plugin in Jellyfin (Dashboard → Plugins → Catalog)
2. In Yamtrack, each user generates their own API token (Settings → Integrations)

### Per-Jellyfin-user tracking

Yamtrack authenticates webhook calls purely by token — it does **not** read the Jellyfin username from
the payload. To keep each household member's watch history separate:

1. Each person creates their own Yamtrack account and copies their token
2. In the Jellyfin Webhook plugin, create **one "Generic Destination" per Jellyfin user**:
   - Destination URL (in-cluster, Jellyfin → Yamtrack directly, no ingress hop):
     `http://yamtrack.yamtrack.svc.cluster.local:8000/jellyfin_webhook/<that-person's-yamtrack-token>/`
   - Filter the destination to that person's Jellyfin user only (per-destination user filter in the plugin)
3. Events to enable: **`Play`** and **`Stop`** only

Without the per-destination user filter, all Jellyfin users' playback would land on a single Yamtrack
account.

### No "Mark as Played/Unplayed" support (yet)

Manually marking an item as watched/unwatched in Jellyfin does **not** sync to Yamtrack — there's no
`MarkPlayed`/`MarkUnplayed` checkbox in the Generic Destination UI, and Yamtrack doesn't currently
process this case. Upstream feature requests are open but unimplemented:
[#790](https://github.com/FuzzyGrim/Yamtrack/issues/790),
[#1524](https://github.com/FuzzyGrim/Yamtrack/issues/1524). The planned fix would watch Jellyfin's
`UserDataSaved` event filtered on `SaveReason == TogglePlayed`, but only `Play`/`Stop` are handled
today. Only actual playback (watching the item) updates Yamtrack.

## Trakt import

Yamtrack has a native Trakt importer (Settings → Import → Trakt), accepting either the Trakt
export file or a direct API connection. Matching is done by TMDB ID, so imported Trakt history
merges with Jellyfin-webhook-driven entries on the same media item.

Recommended order: import Trakt history **before** enabling the Jellyfin webhook, to avoid
duplicate "first watch" entries for titles already marked watched on both sides. Spot-check
in-progress series after import since episode-level progress may differ between sources.

## Release calendar

Yamtrack has its own upcoming-releases calendar (excludes paused/dropped tracking), with:

- iCal (.ics) export for subscribing from an external calendar (e.g. Nextcloud)
- Apprise notifications for upcoming releases (Discord, ntfy, email, etc.)

There is no way to embed this calendar inside the Jellyfin UI — it's only available in the
Yamtrack web UI, the iCal feed, or Apprise push notifications.

## Mobile

No official Android/iOS app exists (feature request open upstream:
[FuzzyGrim/Yamtrack#1246](https://github.com/FuzzyGrim/Yamtrack/issues/1246)). The web UI can be
installed as a PWA from a mobile browser as a substitute.
