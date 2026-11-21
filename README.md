# Tidbyt Monarch

Puts your Monarch Money numbers on a 64x32 pixel display: net worth, savings goal progress, this month's cash flow, and the next bill due.

It renders the frames itself and pushes them to your device. No Starlark, no cloud app, no third party seeing your credentials.

## How it works

1. **Fetch** - logs into Monarch with `monarchmoneycommunity`, reusing a saved session until it expires
2. **Render** - draws one 64x32 WebP frame with PIL (lossless)
3. **Push** - sends it to your Tidbyt cloud device or your own Tronbyt server
4. **Rotate** - sleeps `UPDATE_INTERVAL`, then pushes the next view

By default one frame holds everything: net worth, budget, savings rate and cashflow in a 2x2 grid. Set `VIEWS` to a comma-separated list to rotate full-screen views instead.

## Views

| View | Frame |
|---|---|
| `dashboard` | All four at once in a 2x2 grid: net worth, budget percent, savings rate, cashflow. Three API calls per frame |
| `networth` | Net worth as a big number, assets and liabilities included per Monarch's own setting |
| `budget` | This month's budget: percent used, bar, and totals. Set `BUDGET_CATEGORY` to track one category instead |
| `goal` | One savings goal: name, percent complete, progress bar. Only useful if you have goals in Monarch |
| `cashflow` | This month's net savings, with income and expense on the last line |
| `bill` | The next outgoing recurring bill: name, amount, days until due |

When something breaks, the panel shows a `MONARCH OFFLINE` frame rather than freezing on stale numbers.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONARCH_EMAIL` | Yes | - | Monarch login email |
| `MONARCH_PASSWORD` | Yes* | - | Monarch password (*not needed once a session file exists) |
| `MONARCH_MFA_SECRET` | No | - | TOTP secret from Settings > Security > Enable MFA, needed for unattended re-login |
| `TIDBYT_DEVICE_ID` | Yes | - | Device id on Tidbyt cloud, or the device id in Tronbyt |
| `TIDBYT_API_KEY` | Yes | - | Tidbyt API key, or the per-device key from Tronbyt |
| `TIDBYT_API_BASE` | No | `https://api.tidbyt.com/v0` | Push target. Tronbyt: `http://<host>:<port>/v0` |
| `VIEWS` | No | `dashboard` | `dashboard` for the 2x2 grid, or a comma-separated rotation such as `networth,bill` |
| `BUDGET_CATEGORY` | No | - | Budget category name to track, exact match. Empty shows the month's totals |
| `UPDATE_INTERVAL` | No | `180` | Seconds each view stays on the panel |
| `CACHE_TTL` | No | `10800` | Seconds fetched data is reused before calling Monarch again. `0` disables the cache |
| `GOAL_ID` | No | - | Show a specific savings goal instead of the first active one |
| `TZ` | No | `America/Los_Angeles` | Timezone for logs and "today" |

## First run

Monarch has no developer API. This logs in like the web app does, which means email and password, plus the MFA secret if your account has MFA turned on.

- If you sign in with Google or Apple, set a password first under **Settings > Security**, otherwise there is nothing to log in with.
- Grab `MONARCH_MFA_SECRET` from **Settings > Security > Enable MFA**: the "two-factor text code" value, not one of the 6-digit codes.
- The session is saved to `/data/mm_session.pickle` and reportedly lasts months. Mount `/data` or you will log in fresh on every restart.
- Monarch rate limits by account, which is why the default interval is 60 seconds rather than seconds.

## Running it

```bash
docker compose up -d
```

Or on Unraid, use the template in `templates/tidbyt-monarch-template.xml`.

## Security

Credentials live only in the container. Rendering locally means the frame is pushed as pixels, so nothing about your finances is shared with Tidbyt beyond an image, and with Tronbyt nothing leaves your network at all. The session file is a bearer credential: keep `/data` off shared volumes, and note that `monarchmoneycommunity` writes it world-readable by default.

## Diagnostics

`python -m app.dump` prints the shape of each Monarch payload plus what the parsers extracted. Run it first if a frame shows `n/a`, since Monarch changes its GraphQL fields.

`python -m app.live` renders the real views with your credentials to `/out/live-*.png`, which is the fastest way to see what the panel will show without waiting for a push.

`python -m tools.preview /out` renders every view from synthetic data and asserts nothing touches the frame border.

## Credits

Data access is [monarchmoneycommunity](https://github.com/bradleyseanf/monarchmoneycommunity), an unofficial client. It can break when Monarch changes their API.
