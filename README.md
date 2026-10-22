# Torque

A self-hosted maintenance tracker for dirt bikes. Add your bike, log your rides,
and see what your owner's manual says is due.

No account, no cloud: one container and one SQLite file. Nothing is loaded from
another site, so it works offline.

## Contents

- [What it does](#what-it-does)
- [Bikes included](#bikes-included)
- [Quick start](#quick-start)
- [Develop](#develop)
- [Configuration](#configuration)
- [How it works](#how-it-works)
- [Limits](#limits)
- [Project layout](#project-layout)
- [More docs](#more-docs)
- [Disclaimer](#disclaimer)
- [License](#license)

## What it does

- **Garage:** every bike with a health score and its due counts. Clear a bike's
  history or delete it, one at a time or in bulk.
- **Maintenance:** the manual's schedule as a list of services (3 hours,
  30 hours, ...). Each service is split by system, and each system holds the
  items. Tick items off, or complete a whole service at once. Every item says
  what to do and which manual page it comes from.
- **Rides:** log rides and suspension settings. Rides move the bike's reading
  forward, and you can also set the reading directly.
- **Suspension:** reference settings for the model, when its file provides them.
- **Hours or distance:** engine hours for most bikes, kilometres for
  distance-based manuals, with a per-bike switch to show miles.

## Bikes included

| Model | Manual |
| --- | --- |
| 2026 Beta 125, 200, 250, 300 RR Race | Beta RR 2T owner's manual |
| 2017 KTM 125 XC-W, 250 EXC, 250 XC-W, 300 EXC, 300 XC-W | KTM 2017 owner's manual |
| 2026 Sur-Ron Ultra Bee | Sur-Ron Ultra Bee 2026 owner's manual |

Another bike is a data file, not code. See
[Adding a bike model](docs/adding-a-bike-model.md).

## Quick start

You need Docker with Compose.

```sh
git clone git@github.com:jordantshaw/torque.git
cd torque
docker compose up -d --build
```

Open <http://localhost:8000> and choose **Add a bike**. Your data is in
`./data/app.db` and survives rebuilds. For servers, updates and backups, see
[Deploying](docs/deploying.md).

## Develop

You need Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
DATABASE_URL=sqlite:///./dev.db uv run uvicorn app.main:app --reload
uv run pytest
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:////data/app.db` | The SQLite database. The default is the path inside the container. |
| `BIKE_MODELS_DIR` | `bike_models` | Folder of bike model files, validated at startup. |
| `ALLOWED_HOSTS` | none | Extra host names to serve (names or patterns like `*.lan`). Localhost and IP addresses are always allowed. |
| `TORQUE_USERNAME`, `TORQUE_PASSWORD` | none | Set both to require a login (HTTP Basic). |

If a model file is invalid the app will not start, and the error names the file
and the item.

## How it works

- **Reading.** The latest "set" entry plus every ride after it. It is stored in
  the manual's unit (hours or km); miles are only a display choice.
- **Services.** A service is *overdue* once the reading reaches it, *coming up*
  within 5 hours (50 km), and *done* when every item in it is recorded.
- **Completing.** Marking an item done records the service, the date, the
  reading and any notes.
- **Past the schedule.** The manual only prints so many points. The app only
  projects past the last one when the printed data repeats regularly. Otherwise
  it says "past the manual's schedule" rather than guess.
- **Health.** The share of items that are neither overdue nor coming up.

## Limits

- **No login by default.** Anyone who can reach the app can change everything.
  Keep it on a trusted network, or set a password (see
  [Deploying](docs/deploying.md#keep-it-private)).
- **Time-based intervals** (annual, every 12 months) are not tracked, because
  the app counts hours or distance. Each model lists them in its notes.
- **No reminders.** The app shows what is due; it does not alert you.

## Project layout

```text
app/
  main.py           app factory: loads models, database, templates
  bike_models.py    loads and validates the model files
  models.py, db.py  database tables and sessions
  routes/           pages: home (Garage), bikes, maintenance, rides, suspension
  services/         the logic, with no web code: schedule, due, intervals, hours, units
  templates/        Jinja pages and htmx partials
  static/           style.css and htmx
bike_models/        one YAML file per manual
docs/               guides
tests/              pytest suite
```

Built with FastAPI, SQLAlchemy, Jinja and htmx. There is no JavaScript build.

## More docs

- [Deploying](docs/deploying.md): servers, updates, backups, troubleshooting.
- [Adding a bike model](docs/adding-a-bike-model.md): from owner's manual to
  model file.

## Disclaimer

- Torque is not affiliated with or endorsed by Beta, KTM or Sur-Ron. Those names
  are trademarks of their owners, used only to say which bike a schedule is for.
- The bundled schedules were typed in by hand from the owners' manuals and may
  contain mistakes. Always check your own manual before relying on them, and have
  safety-critical work done by a qualified mechanic. The manuals themselves
  remain their publishers' property; only the intervals are reproduced here.
- Some suspension reference figures come from sheets that are not published.
  A model can read them from a private, git-ignored file (see
  [Adding a bike model](docs/adding-a-bike-model.md#suspension)), so the bundled
  Beta models ship with an empty Suspension tab.

## License

MIT, see [LICENSE](LICENSE). Torque bundles [htmx](https://htmx.org) (0BSD) and
the Manrope typeface (SIL Open Font License; the text is in
`app/static/fonts/OFL.txt`).
