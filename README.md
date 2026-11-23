# Training Coach

Local running coach that imports Garmin activities through the official Personal API, parses FIT files, classifies workouts from lap pace, and writes coaching reports when a Gemini key is configured.

## Architecture

The browser talks only to the Next.js app. Next.js proxies `/backend/*` to the FastAPI process. Garmin and Gemini credentials stay in the API process.

```text
frontend (Next.js) -- /backend/* --> backend (FastAPI) --> Garmin Personal API
                                         |
                                         SQLite now, PostgreSQL later
                                         bearer-token cache in backend/data/
```

Authentication follows the current Personal API:

1. Create a key at [Garmin Connect Personal API Tokens](https://connect.garmin.com/app/settings/personalApiToken).
2. The API exchanges `GARMIN_PERSONAL_API_KEY` for a bearer token with `POST /personalapitoken-service/personal-api/personal-api-key/token` and `Authorization: ApiKey …`.
3. Activity calls use `Authorization: Bearer …`. Tokens last 24 hours. Garmin does not issue refresh tokens, so an expired or rejected token is replaced by exchanging the key again.
4. Activities come from `GET /activitylist-service/activities/search/activities`.
5. Original activity files are downloaded with the official client method `download_activity`, which calls `GET /download-service/files/activity/{activity_id}` and returns ZIP bytes. The FIT file inside is parsed into laps, samples, and workout steps when those messages exist. HTTP 404 is stored as `file_unavailable`. HTTP 403 would mean this key cannot retrieve original files.

The import stores Garmin's activity JSON and copies a measurement only when that field is present. Missing values stay null. Zero values stay zero. `elapsedDuration` is stored as Garmin sent it and is not converted.

Duplicate protection is a unique `(athlete_id, garmin_activity_id)` constraint. A later sync updates the existing row.

Automatic sync uses a background interval (`GARMIN_SYNC_INTERVAL_MINUTES`, default 360). Set it to `0` to disable it. Manual sync is `POST /api/garmin/sync`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Process health |
| `GET` | `/api/garmin/status` | Key configured, token cache, last sync. The key itself is never returned. |
| `POST` | `/api/garmin/sync` | Import activities in the lookback window |
| `GET` | `/api/activities` | Stored activities, newest start time first |
| `GET` | `/api/activities/{activity_id}` | One activity by Garmin activity ID |
| `DELETE` | `/api/activities/{activity_id}` | Delete a stored activity |
| `GET` | `/api/training/summary` | Mileage windows, weekly distance, workout counts, and active days |
| `POST` | `/api/garmin/files` | Download and parse FIT files that are still summary-only |
| `GET` | `/api/garmin/files` | File import counts |
| `POST` | `/api/activities/{activity_id}/file` | Download one original file |
| `PATCH` | `/api/activities/{activity_id}/classification` | Save a workout-type correction |
| `POST` | `/api/activities/{activity_id}/report` | Store an AI report, or refuse when no Gemini key is set |
| `POST` | `/api/coach/chat` | Activity-aware chat that reads stored metrics with tools |
| `GET` | `/api/athlete` | Single local athlete, zones, thresholds, and whether Gemini is configured |
| `PATCH` | `/api/athlete` | Update profile, zones, goal, and saved thresholds |

`POST /api/garmin/sync` accepts an optional JSON body:

```json
{ "lookback_days": 90, "activity_type": "running" }
```

Omit `activity_type` to import every sport in the window. `activity_type` is passed through to Garmin as `activityType`.

## Local setup

Python 3.12 or newer and Node.js are required.

```bash
cp .env.example .env
# Put your Personal API key in GARMIN_PERSONAL_API_KEY.

cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and choose **Sync from Garmin**. The API also listens on http://127.0.0.1:8000.

If port 3000 is already in use, start the frontend with `npx next dev --hostname 127.0.0.1 --port 3010` and open that port instead. The browser calls the API through the Next.js `/backend` proxy, so the API key never reaches the browser.

The database file is `backend/data/coach.db`. The bearer token cache is `backend/data/garmin-bearer-token.json`. Both are gitignored. The cache file is created with permissions restricted to your user.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

Workout labels come from lap duration, distance, and pace. The FIT intensity field is stored and is not used as the label. A saved correction uses source `user` and is kept when the file is parsed again. The November 9, 2026 reference is compared after classification and does not change the math.

Heart-rate drift is calculated only for a steady section of at least 20 minutes whose halves stay within 5 percent pace. Repetitions shorter than 30 seconds are marked so heart rate is not treated as the effort. Lactate threshold is used only when an LT2 pace is saved in Settings.

`GEMINI_MODEL` defaults to `gemini-3.6-flash`. Reports, briefs, plans, and chat require `GEMINI_API_KEY` on the API process. Without it, those endpoints return `gemini_not_configured` and do not invent a report. Netlify does not receive the key.

Nothing in the app changes a training plan. Recommendations stay in the report or the chat.
