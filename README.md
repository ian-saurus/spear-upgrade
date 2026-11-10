# 🗡️ Spear Upgrade

![Gameplay preview](preview.png)

A cartoon Ice Age caveman hunting game. Kill beasts, loot meat/materials/hides,
upgrade your spear, sew disguises, tame baby animals that fight beside you.
Boss every 25 levels, new island after each boss, permadeath throughout.

## Play locally

Open `index.html` in any browser (no build, no server needed).
A synced copy also lives at `~/spear-upgrade.html` for double-click play.

## Deploy

Live site: https://spear-upgrade.vercel.app (auto-deploys on push to `main`).

Manual deploy if needed:

```sh
./deploy.sh
```

## Online accounts + world leaderboard

Same pattern as `neon-survivor`: Python serverless functions in `api/`
(`register`, `login`, `me`, `scores`, `hunt_end`) backed by a shared Vercel
Blob store (`spearupgrade/` prefix), with a local `./data/*.json` fallback.

- Needs `BLOB_READ_WRITE_TOKEN` in the Vercel project (production + preview).
- Run `./tests/run.sh` before pushing: API compile, store units,
  full HTTP round-trip against a temp local store, and a game JS syntax check.
- Note: if the shared Blob store is suspended, writes return
  `503 {"ok": false, "err": "storage busy — retry"}` and the game keeps
  working locally (local profiles + local Hall of Fame are unaffected).

## Controls

- **Spacebar** or ATTACK button — attack
- **E** — eat meat (+100 HP)
- Tabs — upgrade spear 🗡️, sew clothing 🥋, tame/feed babies 🐾
