# Tidbyt Monarch

Puts your Monarch Money numbers on a 64x32 pixel display: net worth, budget used, savings rate, cash flow, and the next bill due.

It renders the frames itself and pushes them to your device. No Starlark, no cloud app, no third party seeing your credentials.

## How it works

1. **Fetch** - logs into Monarch with `monarchmoneycommunity`, reusing a saved session until it expires, and caches the results for `CACHE_TTL`
2. **Render** - draws one 64x32 WebP frame with PIL, lossless
3. **Push** - sends it to your Tidbyt cloud device or your own Tronbyt server, only when the pixels changed
4. **Repeat** - waits `UPDATE_INTERVAL`, then does the next view

By default one frame holds everything: net worth, budget, savings rate and cashflow in a 2x2 grid. Set `VIEWS` to a comma-separated list to rotate full-screen views instead.

## Views

| View | Frame |
|---|---|
| `dashboard` | All four at once in a 2x2 grid: net worth, budget percent, savings rate, cashflow |
| `networth` | Net worth as a big number, assets and liabilities included per Monarch's own setting |
| `budget` | This month's budget: percent used and a progress bar. Set `BUDGET_CATEGORY` to track one category. Month-to-date, so it resets on the 1st |
| `goal` | One savings goal: name, percent complete, progress bar. Only useful if you have goals in Monarch |
| `cashflow` | This month's net savings, with income and expense on the last line. Month-to-date, so it resets on the 1st |
| `bill` | The next outgoing recurring bill: name, amount, days until due |

A dashboard frame costs three API calls, but only when the cache expires, so with the default three-hour TTL that is roughly three calls per three hours rather than per frame.

When a fetch fails the panel shows a `MONARCH OFFLINE` frame instead of freezing on stale numbers. A push failure is handled separately: the session and cache are kept, because a Tronbyt blip should not cost a password login. With Gotify configured you get one alert at the threshold rather than one per cycle.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONARCH_EMAIL` | Yes | - | Monarch login email |
| `MONARCH_PASSWORD` | Yes* | - | Monarch password (*not needed once a session file exists) |
| `MONARCH_MFA_SECRET` | No | - | TOTP seed from Settings > Security > Enable MFA, or an `otpauth://` URI. Needed for unattended re-login |
| `TIDBYT_DEVICE_ID` | Yes | - | Device id on Tidbyt cloud, or the device id in Tronbyt |
| `TIDBYT_API_KEY` | Yes | - | Tidbyt API key, or the per-device key from Tronbyt |
| `TIDBYT_API_BASE` | No | `https://api.tidbyt.com/v0` | Push target. Tronbyt: `http://<host>:<port>/v0` |
| `VIEWS` | No | `dashboard` | `dashboard` for the 2x2 grid, or a rotation such as `networth,bill` |
| `BUDGET_CATEGORY` | No | - | Budget category name to track, matched case-insensitively. Empty shows the month's totals |
| `UPDATE_INTERVAL` | No | `180` | Seconds each view stays on the panel (minimum 10) |
| `CACHE_TTL` | No | `10800` | Seconds fetched data is reused before calling Monarch again. `0` disables the cache |
| `GOAL_ID` | No | - | Show a specific savings goal instead of the first active one |
| `GOTIFY_URL` | No | - | Gotify base URL for failure alerts. Must be an address the container can resolve, e.g. `http://192.168.1.10:8070`; a tailnet MagicDNS name will not resolve inside Docker |
| `GOTIFY_TOKEN` | No | - | Gotify app token |
| `ALERT_AFTER_FAILURES` | No | `2` | Consecutive failed cycles before alerting |
| `ALERT_REPEAT_EVERY` | No | `20` | Repeat the alert every N failures after the first (0 disables repeats) |
| `DEBUG_VALUES` | No | off | Set to `1` to print the actual figures in the container log |
| `PUID` / `PGID` | No | `99` / `100` | User the app runs as, matching appdata ownership |
| `DATA_DIR` | No | `/data` | Where the session file lives inside the container |
| `TZ` | No | `America/Los_Angeles` | Timezone for logs and "today" |

## First run

Monarch has no developer API. This logs in like the web app does, which means email and password, plus the MFA seed if your account has MFA turned on.

- If you sign in with Google or Apple, set a password first under **Settings > Security**, otherwise there is nothing to log in with.
- Grab `MONARCH_MFA_SECRET` from **Settings > Security > Enable MFA**: the "two-factor text code" value, not one of the 6-digit codes. Recovery codes will not work.
- The session is saved to `/data/mm_session.pickle` and reportedly lasts months. Mount `/data` or you will log in fresh on every restart. The file is created `0600`.
- Monarch rate limits by account, which is why the data is cached for hours and the default interval is minutes, not seconds.

## Running it

```bash
docker compose up -d
```

The container starts as root only long enough to take ownership of `DATA_DIR`, then runs the app as `PUID:PGID` (default `99:100`), so bind-mounted appdata keeps working on Unraid.

Or on Unraid, use the template in `templates/tidbyt-monarch-template.xml`, which includes the `/data` path mapping.

## Colours

Captions are always white, so the only colour on screen is the value itself. Values are green when things are fine, red when they want attention, and white when the number is missing:

| Cell | Rule |
|---|---|
| `NW` | Green when net worth is positive, red when negative |
| `BUD` | Green at or under 100% of the month's budget, red above it. Measured against the budget, not against zero |
| `SAVE` | Green at or above a 0% savings rate, red below |
| `CF` | Green when net cashflow is positive, red when negative |

Blue is reserved for data names such as a merchant or a goal title, which are content rather than captions.

## Month-to-date behaviour

`budget` and `cashflow` cover the current calendar month, so both reset on the 1st. Because data is cached for `CACHE_TTL` seconds, the first hours of a new month can still show the previous month's figures until the cache expires. Lower `CACHE_TTL` if that bothers you, or accept a few stale hours once a month.

## Security

Credentials live only in the container. Rendering locally means the frame is pushed as pixels, so nothing about your finances is shared with Tidbyt beyond an image, and with Tronbyt nothing leaves your network at all.

The session file is a bearer credential. The app sets a `077` umask before login and `chmod 0600` after, and the container drops root before running. Keep `DATA_DIR` off shared volumes anyway. Figures are not logged unless you set `DEBUG_VALUES`.

## Diagnostics

`python -m app.dump` prints the shape of each Monarch payload plus what the parsers extracted. Run it first if a frame shows `n/a`, since Monarch changes its GraphQL fields.

`python -m app.live` renders the real views with your credentials to `/out/live-*.png`, the fastest way to see what the panel will show without waiting for a push.

`python -m tools.preview /out` renders every view from synthetic data and asserts nothing touches the frame border.

## Tests

Everything below runs offline, with no Monarch account and no device. CI runs all of it before publishing an image.

```bash
python -m tools.selftest    # currency, layout, colours, parsers, cache, config validation
python -m tools.cycle_test  # scheduler: push-on-change, alert thresholds, error isolation
python -m tools.smoke       # push client against a stub server
```

## Credits

Data access is [monarchmoneycommunity](https://github.com/bradleyseanf/monarchmoneycommunity), an unofficial client. It can break when Monarch changes their API.
