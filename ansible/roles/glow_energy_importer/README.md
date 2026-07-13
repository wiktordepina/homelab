# glow_energy_importer

Imports UK smart-meter electricity data from the Hildebrand / Glowmarkt DCC API
into Home Assistant as **backdated long-term statistics**, feeding the Energy
dashboard.

## Description

Installs a small Python daemon that authenticates against the Glowmarkt API (the
same backend the free Bright app uses), reads *settled* half-hourly consumption,
aggregates it to hourly buckets, and imports those into Home Assistant's recorder
via the WebSocket `recorder/import_statistics` command — each reading placed at the
half-hour it actually occurred.

### Why statistics, not a live sensor

This role replaces the earlier `glow_mqtt_bridge`, which published today's running
total as a live MQTT sensor. The DCC feed is **delayed**: a day's half-hourly
readings only settle around 01:30 the following morning. A live
`total_increasing` sensor timestamps every reading at the moment HA receives it,
so delayed data lands on the wrong hour and "today" is forever near-empty.
External statistics are the only HA mechanism that accepts data at an explicit
historical timestamp, so they are the correct tool for a lagging feed. The trade
is that the Energy dashboard is up to a day behind — which is simply the DCC's
true latency, not a fault.

### Settling, backfill and idempotency

- The importer only touches **fully-settled days** (those whose ending midnight is
  more than two hours in the past), never the unsettled current day.
- It is **append-only**: a per-statistic high-water mark in the systemd
  `StateDirectory` records the last imported hour and its cumulative `sum`; each
  run imports only the hours that have settled since.
- If that state file is lost, the next run **re-imports the whole backfill window
  from zero**, recomputing every `sum` consistently. A wiped `StateDirectory`
  therefore self-heals rather than leaving a `sum` discontinuity that the Energy
  dashboard would render as a spike.
- The `recorder/import_statistics` command upserts by `(statistic_id, start)`, so
  re-importing an hour overwrites it rather than duplicating.

## Statistics

Consumption is always imported. When a tariff is configured, cost and a set of
peak/off-peak and standing/running **split** series are imported too, to feed a
bespoke energy dashboard (multi-perspective hourly charts, week/month-to-date split
cards). The splits are the same fetched half-hours run through different
per-half-hour value functions, so they reconcile exactly against the two base
totals — which are left unchanged so the native HA Energy dashboard keeps working.

| Statistic ID | Unit | When | Meaning |
|---|---|---|---|
| `glow:electricity_consumption` | kWh | always | Total consumption. |
| `glow:electricity_cost` | GBP | tariff | Total cost (running + standing). |
| `glow:electricity_consumption_peak` | kWh | tariff | Consumption in peak-band half-hours. |
| `glow:electricity_consumption_offpeak` | kWh | tariff | Consumption in off-peak half-hours. |
| `glow:electricity_cost_standing` | GBP | tariff | Standing charge only. |
| `glow:electricity_cost_peak` | GBP | tariff | Running charge in peak half-hours. |
| `glow:electricity_cost_offpeak` | GBP | tariff | Running charge in off-peak half-hours. |
| `glow:electricity_cost_dcc` | GBP | `dcc_cost` | DCC-reported cost (dual-source comparison). |

The split IDs and display names are derived from the base
`glow_energy_importer_consumption_id` / `_cost_id` (and their `_name`s), so they
stay consistent with a single knob. Invariants, hour by hour:

- `consumption_peak + consumption_offpeak == consumption`
- `cost_standing + cost_peak + cost_offpeak == cost`

Off-peak is any half-hour whose tariff window is labelled `band: offpeak`; peak is
everything else (including a flat tariff), so the two bands always partition the
total. Before any TOU version takes effect the off-peak series is flat at zero.

### DCC cost (dual-source comparison)

When `dcc_cost` is enabled (default) and the meter exposes a DCC cost resource, the
supplier's own cost figure is imported as `glow:electricity_cost_dcc` for a
side-by-side comparison against the locally-priced cost. The DCC feed is **unit cost
only** — it excludes the standing charge and carries no time-of-use split — so it
lines up against the local **running** charge (`cost_peak + cost_offpeak`), not the
total. It is read from its own resource on its own settle schedule (an independent
fetch and checkpoint) and converted from pence to GBP. If the meter has no cost
resource the series is silently skipped. The comparison exists to judge, from real
data, whether DCC cost can eventually replace the local tariff calculation.

## Tasks

- Installs `python3-venv` and `python3-packaging`.
- Creates a system user `glow-energy-importer`.
- Builds a Python virtual environment under `/opt/glow-energy-importer/venv`.
- Installs `requests`, `PyYAML` and `websocket-client` from the pinned `requirements.txt`.
- Drops the daemon at `/opt/glow-energy-importer/glow_energy_importer.py`.
- Templates `/etc/glow-energy-importer/config.yml` with the API endpoint, Bright
  username, HA URL, poll interval, backfill window and statistic IDs.
- Drops two plaintext secret files (mode `0640`, group-readable by
  `glow-energy-importer`): the Glowmarkt account password and the HA long-lived
  access token.
- Installs and enables a systemd unit with the standard hardening directives and
  a `StateDirectory` for the token cache and import state.

## Requirements

- Debian-based OS with outbound HTTPS to the Glowmarkt API and HTTP reachability
  to the Home Assistant instance.
- A **validated Bright account** with DCC data access for the meter. Registration
  is a manual, human-gated step that can take a couple of days to validate; it is
  tracked as assumed-inputs debt outside this repo.
- A **Home Assistant long-lived access token** for an admin user (Profile →
  Security → Long-lived access tokens). The `recorder/import_statistics` WebSocket
  command requires admin.

## Variables

| Name | Required | Default | Description |
|---|---|---|---|
| `glow_energy_importer_username` | yes | — | Bright account username (the email the meter is registered under). |
| `glow_energy_importer_password_env` | yes | — | Name of the env var on the runner holding the **plaintext** Bright account password. |
| `glow_energy_importer_ha_url` | yes | — | Base URL of the Home Assistant instance, e.g. `http://homeassistant.home.matagoth.com:8123`. |
| `glow_energy_importer_ha_token_env` | yes | — | Name of the env var on the runner holding the HA long-lived access token. |
| `glow_energy_importer_api_url` | no | `https://api.glowmarkt.com/api/v0-1` | Base URL of the Glowmarkt API. |
| `glow_energy_importer_application_id` | no | `b0f1b774-…-27ead8aa7a8d` | Public Bright application ID sent as the `applicationId` header. |
| `glow_energy_importer_poll_interval` | no | `21600` | Seconds between runs. The feed is daily-settled, so a few runs a day is ample. |
| `glow_energy_importer_http_timeout` | no | `30` | Per-request timeout in seconds. |
| `glow_energy_importer_backfill_days` | no | `90` | How far back to import on first run (or after the state file is lost). |
| `glow_energy_importer_timezone` | no | `Europe/London` | Local timezone used to decide day boundaries and settlement. |
| `glow_energy_importer_consumption_id` | no | `glow:electricity_consumption` | External statistic ID for consumption (must contain a `:`). |
| `glow_energy_importer_consumption_name` | no | `Electricity consumption` | Display name for the consumption statistic. |
| `glow_energy_importer_cost_id` | no | `glow:electricity_cost` | External statistic ID for cost (must contain a `:`). |
| `glow_energy_importer_cost_name` | no | `Electricity cost` | Display name for the cost statistic. |
| `glow_energy_importer_currency` | no | `GBP` | Currency unit for the cost statistic. |
| `glow_energy_importer_dcc_cost` | no | `true` | Import the DCC's own cost figure as `glow:electricity_cost_dcc` for comparison. Auto-disabled if the meter has no cost resource. |
| `glow_energy_importer_tariffs` | no | `[]` | Date-effective time-of-use tariff (see below). Empty disables cost import. |

## Tariff

The DCC cost and tariff feeds advertise only the supplier's flat import rate (not a
time-of-use split) and omit the standing charge, so cost is computed locally from
`glow_energy_importer_tariffs` — a list of **date-effective versions**. The
version in force on a given local day is the latest one whose `effective_from` is
on or before it, so a supplier or rate change is just a new entry with a later
date, and historical days keep being priced by the tariff that applied then.

Each version has a `standing_charge` (GBP/day) and a list of `unit_rates`
(GBP/kWh). A rate with neither `from` nor `to` is a flat all-day rate; otherwise
each window is local clock time and a window whose `from` is later than its `to`
wraps past midnight (e.g. an overnight off-peak). Each settled hour is priced by
the window covering it, and the day's standing charge is spread evenly across its
hours.

A window may also carry a `band` label — `peak` or `offpeak`. It does not affect
pricing; it drives the peak/off-peak split statistics (see [Statistics](#statistics)).
An unlabelled window is `peak`, so a flat tariff is entirely peak and off-peak is
only ever a window explicitly labelled `band: offpeak`.

```yaml
glow_energy_importer_tariffs:
  - effective_from: "2025-01-01"      # flat
    standing_charge: 0.5395
    unit_rates:
      - { rate: 0.2495 }
  - effective_from: "2026-07-08"      # on/off-peak (EV)
    standing_charge: 0.5710
    unit_rates:
      - { from: "23:00", to: "06:00", rate: 0.0699, band: offpeak }  # wraps midnight
      - { from: "06:00", to: "23:00", rate: 0.3028, band: peak }
```

Cost is append-only like consumption: editing a tariff only re-prices hours
imported *after* the change. To re-price already-imported history (e.g. after
correcting a rate), delete the cost entry from
`/var/lib/glow-energy-importer/import_state.json` and restart — the next run
re-imports the backfill window at the corrected rates.

## Dependencies

- `base` (apt update/upgrade).

## Example usage

```yaml
ansible:
  roles:
    - base
    - role: glow_energy_importer
      vars:
        glow_energy_importer_username: someone@example.com
        glow_energy_importer_password_env: GLOW_BRIDGE_PASSWORD
        glow_energy_importer_ha_url: http://homeassistant.home.matagoth.com:8123
        glow_energy_importer_ha_token_env: GLOW_IMPORTER_HA_TOKEN
```

## Credentials

Both secrets are sourced from runner env vars named by the `*_env` variables,
added alongside the other runner secrets (e.g. in `/pve/secrets/`):

```bash
export GLOW_BRIDGE_PASSWORD='<bright-account-password>'
export GLOW_IMPORTER_HA_TOKEN='<ha-long-lived-access-token>'
```

## Wiring the Energy dashboard (manual HA step)

External statistics appear in **Settings → Devices & services → Statistics**, but
are not auto-added to the Energy dashboard. Once data has imported, go to
**Settings → Dashboards → Energy → Electricity grid → Add consumption**, pick
`glow:electricity_consumption`, then under **Use an entity tracking the total
costs** select `glow:electricity_cost`. This UI step lives outside the repo and is
tracked as assumed-inputs debt.

## Verifying the import

```bash
# On the importer host, watch the daemon journal:
./run/host-ssh 214 journalctl -u glow-energy-importer -f
```

Expect, per run, an `imported N hour(s) into <statistic_id> up to <ts>
(cumulative …)` line per statistic when new settled hours exist, or
`nothing new settled since last import` otherwise. The imported daily totals should
match the Bright app's per-day figures.

## Tests

Pure-logic unit tests (tariff rate/band resolution, date-effective versioning, and
the peak/off-peak & standing/running split invariants) live under `tests/` and need
no dependencies — the network deps are stubbed:

```bash
cd ansible/roles/glow_energy_importer && python3 -m unittest discover -s tests
```

## Notes

- DCC readings are delayed by ~a day; the Energy dashboard will be correspondingly
  up to a day behind. This is expected, not a fault.
- The auth token is long-lived (~18 months observed) and persisted to
  `/var/lib/glow-energy-importer/token.json` so restarts do not re-authenticate.
- The **authoritative** cost is priced locally, not read from the DCC: the DCC cost
  and tariff feeds advertise only the supplier's flat import rate (no time-of-use
  split) and omit the standing charge, so they cannot price a time-of-use tariff. A
  configured, date-effective tariff computes the cost statistics — see
  [Tariff](#tariff) above. The DCC's own cost figure is imported *alongside* it,
  purely for comparison — see [DCC cost](#dcc-cost-dual-source-comparison).
