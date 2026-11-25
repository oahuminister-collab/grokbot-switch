# GrokBot switch

Want your AI agents to use your spare computer power without getting in your way? GrokBot Switch sits on your desktop as a small red and green toggle. Before an agent starts a job on your PC, it checks the switch. If you're busy, it moves on. If you're free, it can ask first with a popup, and if you don't answer in 5 minutes, it goes ahead.

A tiny always-on-top desktop switch.
Green means **Available**. Red means **Do Not Disturb**.
Bots check the switch before they use this PC, so they do not interrupt you.

## What it does

- An always-on-top pill shows the current state. Click the pill to flip it by hand. Click **–** to shrink it to a 28px status dot; click the dot to bring the pill back. The dot stays green or red as availability changes, and permission popups still appear while it is minimized.
- A settings window lets you add or remove schedule rules (days, start, end, Available or Do Not Disturb), turn on auto Do Not Disturb while you are using the PC, turn Available back on after you have been idle, and ask before a bot uses the PC (with an optional auto-allow timer).
- If a bot is using the PC and you start typing or moving the mouse, the switch turns red, the bot’s lease is revoked, and the bot should stop and move the job to your other computer.
- Right-click the pill (or the minimized dot) and choose Exit to close the switch. There is no system tray icon in this version.

A new install starts with an empty schedule; add times in settings if you want one. A schedule stays in force even if the PC is idle. A manual click holds until the next scheduled time, or until you start or stop using the PC in a way that should change it.

## Install

You need Python 3.10 or newer. The usual Windows installer includes tkinter — check the tcl/tk box if it asks. No other packages are required.

1. Copy this folder to a place on the Windows PC you want to share, for example `%USERPROFILE%\GrokBotSwitch\`.
2. Run the app with `pythonw` so no extra console window stays open:

       pythonw grokbot_switch_app.py

3. Leave **Start with Windows** off unless you turn it on in settings. That option only adds a small file in your Startup folder. It does not use Task Scheduler.

Linux works well enough for development and tests. The rounded corners and click-through chrome are designed for Windows.

## Bot-check CLI

Before a job starts:

    python grokbot_check.py --bot "My Bot" --job "research" --minutes 3

- Exit 0 means go ahead. The JSON line includes `lease_id`.
- Exit 1 means no (Do Not Disturb, or you declined).

Open bot windows minimized or in the background when you can, so they do not jump in front of you.

## Heartbeat and yield

While the job runs, about every 10 seconds:

    python grokbot_check.py --heartbeat LEASE_ID

If that exits 1, stop cleanly, close any windows you opened, and move the job to your other computer. The switch will show: “\<bot> stopped. Moving the job to your other computer.”

When the job finishes normally:

    python grokbot_check.py --release LEASE_ID

## Config

Config and status live in `%LOCALAPPDATA%\GrokBotSwitch\` (or `~/GrokBotSwitch` on Linux):

- `config.json`
- `status.json`
- `leases\` (one file per bot job)

Set the `GROKBOT_SWITCH_APPDATA` environment variable to use a different folder. Useful keys in `config.json`:

- `schedule` — a list of rules; empty by default
- `auto_dnd_when_active` — turn red while you are using the PC
- `idle_minutes` — turn Available after this much idle time
- `ask_before_use` — show a permission popup
- `auto_allow_minutes` — if there is no answer, allow after this many minutes
- `start_with_windows` — off by default
- `ipc_port` — local port for the CLI (default 47281)
- `yield_grace_seconds` — how quickly a yield is applied
- `widget_position` and `widget_minimized` — remembered pill placement and whether it is minimized

The CLI talks to the running widget over localhost. If the widget is not running, a check fails fast instead of waiting.

## License

MIT. See `LICENSE`.
