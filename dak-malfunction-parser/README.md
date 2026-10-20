# dak-malfunction-parser

Parses Daktronics Omnisport 2000 timing logs to reconstruct a race when
the console malfunctions: per-lane touchpad and button times measured
from the start signal, with events the timer could not have scored
flagged rather than dropped.

The whole log file is treated as one race. The first Start-Close event is
t=0, and race-number changes partway through the file are ignored.
Events whose embedded time is 0.00 are marked INVALID, because the timer
was not running when they fired. Touchpad hits inside the pre-arm window,
and any after a lane's first valid touch, are FILTERED.

## Usage

Standard library only, so it needs no install step:

```bash
python3 parse_timing.py <logfile>                  # console table
python3 parse_timing.py <logfile> --csv            # CSV to stdout
python3 parse_timing.py <logfile> --markdown       # Markdown to stdout
python3 parse_timing.py <logfile> --csv -o out.csv # write to a file
python3 parse_timing.py <logfile> --arm-delay 15   # pre-arm window in seconds (default 10, 0 disables)
python3 parse_timing.py <logfile> -v               # also show INVALID/FILTERED events
```

`--csv` and `--markdown` are mutually exclusive.

## Data

[data/](data/) holds sample logs from a real session malfunction, used to
check the parser by hand. There are no automated tests yet.
