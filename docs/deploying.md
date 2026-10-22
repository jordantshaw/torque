# Deploying Torque

One container, one port, one SQLite file.

## Contents

- [Deploy](#deploy)
- [Change the port](#change-the-port)
- [Keep it private](#keep-it-private)
- [Update](#update)
- [Back up and restore](#back-up-and-restore)
- [Add or edit bike models](#add-or-edit-bike-models)
- [Everyday commands](#everyday-commands)
- [Troubleshooting](#troubleshooting)

## Deploy

You need a machine that stays on, with Docker and the Compose plugin.

```sh
git clone git@github.com:jordantshaw/torque.git
cd torque
docker compose up -d --build
```

Open `http://<machine>:8000`. The database is created at `./data/app.db`, on the
host, so it survives rebuilds and `docker compose down`.

## Change the port

Edit the left-hand number in `docker-compose.yml`, then recreate the container:

```yaml
    ports:
      - "9000:8000"   # host:container
```

```sh
docker compose up -d
```

## Keep it private

Torque is built for a trusted network. By default it:

- serves only `localhost` and IP addresses, and refuses other host names (this
  blocks DNS-rebinding attacks);
- refuses state-changing requests that a browser says came from another site, so
  a web page you visit can't delete your bikes;
- sends strict security headers, including a Content-Security-Policy that
  allows no inline scripts;
- accepts only plain form posts of at most 1 MB, counted as they stream in;
- loads everything (scripts, styles, the typeface) from the app itself, never
  from another site;
- runs as an unprivileged user, with a read-only filesystem and no extra
  capabilities.

It has **no login unless you set one**. Anyone who can reach the port can read,
change and delete everything. Pick at least one of these.

**Require a password.** Create a file named `.env` next to `docker-compose.yml`
(it is git-ignored):

```sh
TORQUE_USERNAME=rider
TORQUE_PASSWORD=a-long-passphrase
```

Then run `docker compose up -d`. The browser asks once.

- A client that gets the password wrong 10 times is locked out for about
  5 minutes, even if it then tries the right one.
- HTTP Basic sends the password with every request, so use it over HTTPS or a
  VPN, not plain HTTP on a network you don't trust.
- The password is stored in plain text in `.env`, and anyone who can run
  `docker inspect` can read it. Keep the file private (`chmod 600 .env`).
- Behind a reverse proxy every visitor shares the proxy's address, so one
  client's failed guesses lock everyone out. Put the login on the proxy instead.

**Reach it by a name.** Names such as `nas.local` or a Tailscale name are refused
by default. Allow them in `.env`:

```sh
ALLOWED_HOSTS=nas.local,*.lan     # names or patterns; * allows any name
```

`ALLOWED_HOSTS=*` switches the DNS-rebinding protection off, so combine it with a
password.

**Or keep it off the network.** Use a VPN such as Tailscale or WireGuard, or put
a reverse proxy with HTTPS in front and bind the app to localhost:
`- "127.0.0.1:8000:8000"`. Make the proxy pass the original `Host` header.

Never publish the port straight to the internet.

## Update

```sh
git pull
docker compose up -d --build
```

Your data is untouched. If an update adds a database column, the app adds it on
startup. Back up first if you want to be safe, then hard-refresh the browser
(Cmd/Ctrl+Shift+R) so it drops the cached stylesheet.

## Back up and restore

Everything you enter is in `data/app.db`. Back up that one file.

```sh
sqlite3 data/app.db ".backup 'torque-backup.db'"
```

This is safe while the app is running. Copy the result to a different disk or
machine. Without `sqlite3`, run `docker compose stop`, copy `data/app.db`, then
`docker compose start`.

To restore, or to move to a new machine:

```sh
docker compose stop
cp torque-backup.db data/app.db
docker compose start
```

A nightly backup, as a cron job (create `backups/` first):

```sh
0 3 * * * cd /path/to/torque && sqlite3 data/app.db ".backup 'backups/app-$(date +\%F).db'"
```

## Add or edit bike models

Model files are copied into the image when it is built, so a change needs a
rebuild:

```sh
docker compose up -d --build
```

To edit them often, mount the folder instead. Create
`docker-compose.override.yml` next to the compose file (Compose reads it
automatically):

```yaml
services:
  web:
    volumes:
      - ./bike_models:/app/bike_models:ro
```

Then `docker compose up -d` once, and `docker compose restart` after each edit.
How to write a model is in [Adding a bike model](adding-a-bike-model.md).

## Everyday commands

| Command | Does |
| --- | --- |
| `docker compose ps` | Shows whether it is running |
| `docker compose logs -f web` | Follows the logs |
| `docker compose restart` | Restarts without rebuilding |
| `docker compose stop` | Stops it; data is kept |
| `docker compose down` | Removes the container; data is kept |

Only deleting the `data/` folder removes your records.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Page won't load, but the container is running | Another program may hold port 8000. Run `lsof -nP -iTCP:8000 -sTCP:LISTEN`. Stop it, or change the port. Two programs on one port can look like the app "sometimes works". |
| Container exits right after starting | Run `docker compose logs web`. A model file failed validation; the message names the file and item. |
| Updated, but the page looks the same | Rebuild with `docker compose up -d --build`, then hard-refresh. |
| A bike shows an error | Its model file is missing or its `key` was changed. Restore the file. Never rename a `key` that bikes use. |
| `Unknown host name` (a 400) | You reached it by a name that isn't allowed. Add it to `ALLOWED_HOSTS` in `.env`. |
| `Too many failed logins` (a 429) | Wait the number of seconds in the `Retry-After` header (up to 5 minutes), or restart the container. |
| `Cross-site request blocked` (a 403) | A request came from another site, or a proxy changed the `Host` header. Use the app directly, or make the proxy pass the original `Host`. |
| Permission error on `./data` (Linux) | The container runs as uid 1000. Run `chown -R 1000:1000 data`, or set `TORQUE_UID` and `TORQUE_GID` in `.env` to your own ids. |
| Start with a clean slate | Stop the app, move `data/app.db` aside, start it again. |
