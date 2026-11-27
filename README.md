# MikroTik Real-Time Monitor

A compact dark-mode desktop dashboard for a MikroTik router on Windows.
It polls SNMP once per second and shows CPU, RAM, temperature, voltage,
active users, rolling ping latency/loss and two scrolling traffic charts.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ MikroTik Real-Time Monitor            [● ONLINE]        UPTIME 3d 04:12  │
│ MIKROTIK-ROUTER1 · 192.168.88.1                                          │
├───────────────────────┬──────────────────────────────────────────────────┤
│ SYSTEM                │ ● UPLINK ether1              [LINK 1.0 Gbps]     │
│ CPU LOAD        23%   │ RX 45.2 Mbps   TX 9.4 Mbps                       │
│ ▓▓▓▓▓▓░░░░░░░░░░░░░░  │        ╱╲    ╱╲___╱╲                             │
│ MEM USED        54%   │  ___╱  ╲__╱        ╲___                          │
│ ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░  │                                                  │
│ TEMP 41.2 °C  VOLT 23.8 V │ ● SFP+ sfp1               [LINK 10.0 Gbps]  │
│                       │ RX 120.4 Mbps  TX 22.1 Mbps                      │
│ LATENCY      60s window│       ╱╲╱╲                                       │
│ Google DNS   8.8.8.8  │  ____╱    ╲___                                   │
│ AVG 12.4 ms   LOSS 0.0%│                                                 │
│ Game Server  1.1.1.1  │                                                  │
│ AVG 18.7 ms   LOSS 1.7%│                                                 │
│                       │                                                  │
│ ACTIVE USERS          │                                                  │
│ 42                    │                                                  │
└───────────────────────┴──────────────────────────────────────────────────┘
```

## Requirements

- Windows 10 (1809 or later) or Windows 11, 64-bit
- Python 3.10 or newer (tested on 3.14) — only for running from source;
  the portable EXE in `Release` needs no Python at all
- SNMP enabled on the router (read-only community is enough)
- Optional: RouterOS API user for accurate PPPoE/HotSpot session counts

## Install

```powershell
cd mikrotik-monitoring-phy
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.yaml config.yaml
```

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Enable SNMP on RouterOS

In WinBox / WebFig or the terminal:

```routeros
/snmp community
add name=monitor addresses=192.168.88.0/24 read-access=yes
/snmp
set enabled=yes
```

Then set `router.snmp.community` in `config.yaml` to `monitor`
(or keep the default `public` if you already use that).

Verify from Windows:

```powershell
# Any SNMP tool works; the monitor itself is the real test.
.\.venv\Scripts\python.exe main.py --demo   # UI preview without a router
.\.venv\Scripts\python.exe main.py
```

## Optional: RouterOS API

SNMP cannot report PPPoE session counts on RouterOS, so enable the API if
you want an exact **Active Users** figure:

```routeros
/ip service enable api
/ip service set api address=192.168.88.0/24
/user add name=monitor group=read password="a-strong-password"
```

```yaml
router:
  api:
    enabled: true
    username: "monitor"
    password: "${MIKROTIK_PASSWORD}"
```

The API also provides exact CPU/RAM/uptime, which take precedence over the
SNMP values when enabled. Use `use_ssl: true` and `port: 8729` for api-ssl.

## Configure

`config.yaml` is commented; the important keys:

| Key | Meaning |
| --- | --- |
| `router.host` | Router IP or DNS name |
| `router.snmp.community` | SNMPv2c read community |
| `router.snmp.timeout` / `retries` | Per-request timeout and retries |
| `polling.interval` | Seconds between samples (`1.0` default) |
| `polling.history_seconds` | Chart history length |
| `interfaces[].name` | `ifName` or `ifDescr` of the port to chart |
| `interfaces[].label` | Title shown above the chart |
| `ping.targets[].host` | ICMP latency targets |
| `ping.window` | Rolling window for average/loss (seconds) |
| `oids.*` | Optional OID overrides (empty = auto-detect) |

The V6/V7 choice only changes the dashboard label and whether the RouterOS
API collector is enabled (it needs a login). The SNMP OIDs used by this app
are common to both versions, so there is no separate OID set for V6.

Secrets can stay out of the file:

```yaml
password: "${MIKROTIK_PASSWORD}"
```

`${NAME}`, `$NAME` and `%NAME%` are all expanded from the environment.

## Run

Double-click `run.vbs` for a windowless launch (no console window), or
`run.bat` for console/debug mode:

```powershell
.\run.bat
```

On startup the app opens the **Login SNMP Mikrotik** setup screen first.
There you enter (or pick a saved) router profile: IP address, RouterOS
login/password, SNMP community, API port, RouterOS version (V6/V7) and the
router identity. Use **Scan** to discover interfaces, **Use** to add them to
the monitored list, then **Save** and **Connect** to open the live dashboard.
Profiles are stored in `routers.json` next to the app, so switching between
routers (e.g. `core-router`, `office-switch`) is one click. Passwords
are encrypted with Windows DPAPI for the current Windows user, so after
copying `routers.json` to another PC the password must be typed again. The
dashboard header has a **Disconnect** button that stops all polling/threads
and returns to this screen with all saved profiles intact.

- **SwOS support**: choose `SwOS` in the RouterOS Version selector for MikroTik
  switches. SNMP-only monitoring (identity, uptime, ports, link speed, Tx/Rx);
  router-only metrics (Active Users, Temp/Volt when unavailable) show `N/A`/`--`.
- **Link speed**: each interface header shows the negotiated speed (`10G`, `1G`,
  `100M`, `10M`) or `Link Down`, from `ifHighSpeed`/`ifSpeed` + `ifOperStatus`.

`run.bat` uses the project virtual environment, works no matter which folder
it is launched from, and keeps the console open if the app exits with an error
so you can read the message. Arguments are passed straight through:

```powershell
.\run.bat --demo                       # synthetic data, no router required
.\run.bat --config other.yaml --verbose # load a legacy config.yaml directly
```

You can also call the interpreter directly:

```powershell
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe main.py --help
```

## Portable EXE (folder `Release`)

`build_exe.bat` builds a single-file, windowed executable with PyInstaller and
refreshes the `Release` folder:

```
Release\
  Mikrotik-Realtime-Monitor.exe   portable app (no Python required)
  config.example.yaml             optional reference configuration
  routers.json                    empty profile store (no credentials shipped)
  Demo.bat                        preview the UI with synthetic data
  README.txt                      Indonesian quick-start guide
```

Run `build_exe.bat` from the project folder (it uses `.venv`). The executable
targets 64-bit Windows 10 (1809 or later) and Windows 11; the Visual C++
runtime and Qt platform/multimedia plugins are bundled, so no extra installers
are needed. The build is unsigned, so SmartScreen may ask for confirmation the
first time it runs on another PC.

## How it works

```
app/config.py       typed YAML loading + validation
app/snmp_client.py  stdlib SNMPv2c GET/GETNEXT client (no native deps)
app/collector.py    SNMP / API / ping worker threads + thread-safe state
app/ping.py         system ping probe + rolling 60 s window
app/routeros_api.py optional librouteros wrapper
app/metrics.py      bps maths and formatting
app/ui.py           PySide6 window, cards and pyqtgraph charts
app/setup.py        Login SNMP Mikrotik profile screen
app/profiles.py     router profile store (routers.json)
main.py             entry point
```

**Traffic rates.** `ifHCInOctets` / `ifHCOutOctets` (Counter64) are read once
per second and converted with `(octets_now - octets_prev) * 8 / Δt`. If the
64-bit counters are unavailable the collector falls back to 32-bit
`ifInOctets` / `ifOutOctets`, including a wrap correction at 2^32. The first
sample after startup has no delta, so it shows `--` for one second.

**Health.** CPU uses the MikroTik processor-load scalar when present and
otherwise averages the HOST-RESOURCES `hrProcessorLoad` table. RAM comes from
the `hrStorage` row labelled RAM. Temperature and voltage use the MIKROTIK-MIB
OIDs, whose `DISPLAY-HINT "d-1"` means tenths (values below 100 are treated as
whole units for routers that report them that way).

**Active users.** With the API enabled this is
`/ppp/active` + `/ip/hotspot/active` row count. Without it the collector reads
`mtxrHotspotActiveUserCount`, which only counts HotSpot clients (0 on a pure
PPPoE router). Point `oids.active_users` at another counter OID if you have one.

**Resilience.** All I/O happens on worker threads. A failed SNMP request
closes the socket, backs off, reconnects and re-resolves interfaces; the UI
keeps rendering the last values and flips the status pill to
`DEGRADED`/`OFFLINE`. Ping failures only affect the latency cards.

## Tests

Unit tests cover the shared rate/formatting maths, neutral config defaults,
secret protection and profile persistence (including legacy plain-text
password migration):

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `OFFLINE`, footer shows a timeout | Router IP, `snmp.enabled`, Windows firewall, community name |
| Charts empty but health works | `interfaces[].name` must match `ifName`; the chart header says `NOT FOUND` when it does not |
| Temp / Volt show `--` | Not every model has sensors; try the board OIDs in `config.example.yaml` comments |
| Active Users shows 0 | HotSpot count only; enable `router.api` for PPPoE |
| Ping loss is 100% | The target blocks ICMP, or a local firewall does |
| `Configuration error: ...` | The message names the offending key |
| Scan returns no interfaces | SNMP community/host wrong, or router blocks SNMP; check firewall |
| Identity stays empty | Router identity not set; type it manually, or enable API |
| API collector `invalid user name or password` | Fix login/password (or disable API by clearing login) |
| Active Users shows `--` | No PPPoE sessions and no hotspot; or enable API for exact counts |

List interface names on the router:

```routeros
/interface print where type=ether
```

or walk `1.3.6.1.2.1.31.1.1.1.1` with any SNMP tool.

## Notes

- The SNMP client is a small stdlib implementation, so there is no
  `pysnmp`/`easysnmp` build step on Windows. `app/snmp_client.py` exposes
  `get()` / `walk()`, so it can be swapped for another backend without
  touching the collector.
- Charts keep `history_seconds` of samples; at the default 1 s interval that
  is 120 points per interface.
- The dashboard is read-only: it never writes configuration to the router.
