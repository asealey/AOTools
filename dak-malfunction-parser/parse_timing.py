#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Adam Sealey

"""
Daktronics Omnisport 2000 timing log parser.

Treats the entire log file as a single race. The first Start-Close event
found is used as t=0. Race number changes mid-file (e.g. operator assigning
the race number late) are ignored — all lane events are merged into one race.

Events with embedded time of 0.00 are flagged INVALID — the Daktronics timer
was not running when they fired (race number not assigned before gun fired).
Their wall-clock elapsed is still shown for reference.

Usage:
    python3 parse_timing.py <logfile>              # console output
    python3 parse_timing.py <logfile> --csv        # CSV to stdout
    python3 parse_timing.py <logfile> --markdown   # Markdown to stdout
    python3 parse_timing.py <logfile> --csv -o results.csv
    python3 parse_timing.py <logfile> --markdown -o results.md
    python3 parse_timing.py <logfile> --arm-delay 15   # custom arm window
    python3 parse_timing.py <logfile> --arm-delay 0    # disable touchpad filtering
    python3 parse_timing.py <logfile> -v               # include INVALID/FILTERED events
"""

import argparse
import csv
import io
import math
import re
import sys
from datetime import datetime
from collections import defaultdict


# Matches starred event lines that carry a wall-clock timestamp, e.g.:
#   *514   7)        10:42:14.735      30.41  Touchpad Near-Close
#   *513    )        10:41:44.320      53.27  Start-Close
STARRED_EVENT_RE = re.compile(
    r'^\*\s*(\d+)\s+(\d*)\)\s+(\d{2}:\d{2}:\d{2}\.\d{3})\s+([\d.]+)\s+(.+?)\s*$'
)

TIME_FMT = '%H:%M:%S.%f'


def parse_wall_time(s: str) -> datetime:
    # strptime %f parses up to 6 digits; pad milliseconds to microseconds
    return datetime.strptime(s + '000', TIME_FMT)


def fmt_time(dt: datetime) -> str:
    return dt.strftime('%H:%M:%S.') + f'{dt.microsecond // 1000:03d}'


def fmt_elapsed(seconds: float) -> str:
    """Truncate to hundredths, format as M:SS.hh (swim-timing convention)."""
    truncated = math.floor(seconds * 100) / 100
    m = int(truncated // 60)
    s = truncated % 60
    return f"{m}:{s:05.2f}"  # e.g. 0:30.41


EVENT_ORDER = {'Touchpad': 0, 'Button 1': 1, 'Button 2': 2}

def lane_sort_key(ev: dict):
    return (EVENT_ORDER.get(ev['event_type'], 9), ev['wall_time'])


def parse_log(filepath: str) -> dict:
    """
    Returns a single race dict representing the entire file:
        {
            'start':        datetime | None,
            'start_source': str,
            'events': [
                {
                    log_race_num,               # race number as it appeared in the log
                    lane, wall_time, embedded_time,
                    event_type, raw_event,
                    valid,                      # False if embedded_time == 0.00
                    elapsed,                    # seconds from start (wall-clock), or None
                    filter_reason,              # set by apply_touchpad_filter(), else None
                }
            ]
        }
    """
    race = {
        'start':        None,
        'start_source': 'not found',
        'events':       [],
    }

    with open(filepath, 'r') as f:
        lines = f.readlines()

    for line in lines:
        line = line.rstrip()
        m = STARRED_EVENT_RE.match(line)
        if not m:
            continue

        log_race_num = int(m.group(1))
        lane_raw     = m.group(2)       # empty string for non-lane events (Start, etc.)
        wall_time    = parse_wall_time(m.group(3))
        embedded     = float(m.group(4))
        event        = m.group(5).strip()
        lane         = lane_raw if lane_raw else None

        # ── Start signal ──────────────────────────────────────────────────────
        if 'Start-Close' in event and lane is None:
            if race['start'] is None:           # use first one found
                race['start'] = wall_time
                race['start_source'] = f'Start-Close in log (logged as race {log_race_num})'
            continue

        # ── Lane events ───────────────────────────────────────────────────────
        if lane is None:
            continue

        event_type = None
        if 'Touchpad' in event:
            event_type = 'Touchpad'
        elif 'Button 1' in event:
            event_type = 'Button 1'
        elif 'Button 2' in event:
            event_type = 'Button 2'

        if event_type is None:
            continue

        race['events'].append({
            'log_race_num':  log_race_num,
            'lane':          lane,
            'wall_time':     wall_time,
            'embedded_time': embedded,
            'event_type':    event_type,
            'raw_event':     event,
            'valid':         embedded > 0.0,
            'elapsed':       None,
            'filter_reason': None,
        })

    # ── Compute elapsed for all events ────────────────────────────────────────
    start = race['start']
    if start:
        for ev in race['events']:
            ev['elapsed'] = (ev['wall_time'] - start).total_seconds()

    return race


def apply_touchpad_filter(race: dict, arm_delay: float) -> None:
    """
    For each lane, mark touchpad events as filtered:
      - 'pre-arm'     : elapsed < arm_delay (fired before system is armed)
      - 'post-finish' : any touchpad after the first valid, armed one

    Button events are not affected. Modifies race in-place.
    """
    lanes: dict = defaultdict(list)
    for ev in race['events']:
        lanes[ev['lane']].append(ev)

    for lane_events in lanes.values():
        touchpads = [
            ev for ev in lane_events
            if ev['event_type'] == 'Touchpad' and ev['elapsed'] is not None
        ]
        found_first = False
        for ev in sorted(touchpads, key=lambda e: e['wall_time']):
            if ev['elapsed'] < arm_delay:
                ev['filter_reason'] = f'pre-arm (<{arm_delay}s)'
            elif found_first:
                ev['filter_reason'] = 'post-finish (duplicate touchpad)'
            else:
                found_first = True              # first armed touchpad = keeper regardless of embedded time


# ── Output: console ───────────────────────────────────────────────────────────

def is_keeper(ev: dict) -> bool:
    # Buttons always show — the physical press is real even if embedded time was 0.00.
    # Touchpads are filtered by arm delay and first-only logic.
    if ev['event_type'] != 'Touchpad':
        return True
    return ev['filter_reason'] is None


def output_console(race: dict, verbose: bool = False) -> str:
    out   = io.StringIO()
    start = race['start']

    out.write(f"\n{'=' * 56}\n")
    if start:
        out.write(f"  Start signal : {fmt_time(start)}\n")
        if verbose:
            out.write(f"  Source       : {race['start_source']}\n")
    else:
        out.write(f"  Start signal : NOT FOUND\n")
    out.write(f"{'=' * 56}\n")

    if not race['events']:
        out.write("  No lane events found.\n\n")
        return out.getvalue()

    lanes: dict = defaultdict(list)
    for ev in race['events']:
        lanes[ev['lane']].append(ev)

    for lane in sorted(lanes.keys(), key=int):
        lane_events = sorted(lanes[lane], key=lane_sort_key)

        # In non-verbose mode skip lanes that have no keeper events at all
        if not verbose and not any(is_keeper(ev) for ev in lane_events):
            continue

        out.write(f"\n  Lane {lane}:\n")
        for ev in lane_events:
            keeper = is_keeper(ev)

            # Non-verbose: skip non-keepers entirely
            if not verbose and not keeper:
                continue

            elapsed_str = fmt_elapsed(ev['elapsed']) if ev['elapsed'] is not None else 'N/A'

            if verbose:
                if not ev['valid']:
                    tag  = '[no timer]'
                    note = '  ← embedded time was 0.00 (race number not set)'
                elif ev['filter_reason']:
                    tag  = '[FILTERED]'
                    note = f'  ← {ev["filter_reason"]}'
                else:
                    tag  = '          '
                    note = ''
                calc = f"  ({fmt_time(ev['wall_time'])} - {fmt_time(start)})" if ev['elapsed'] is not None else ''
                out.write(
                    f"    {tag}  {ev['event_type']:<10}  {elapsed_str}"
                    f"{calc}  [log race {ev['log_race_num']}]{note}\n"
                )
            else:
                out.write(f"    {ev['event_type']:<10}  {elapsed_str}\n")

    out.write('\n')
    return out.getvalue()


# ── Output: CSV ───────────────────────────────────────────────────────────────

CSV_FIELDS_BRIEF   = ['start_time', 'lane', 'event_type', 'elapsed_s']
CSV_FIELDS_VERBOSE = ['start_time', 'start_source', 'lane', 'log_race_num',
                      'event_type', 'wall_time', 'elapsed_s', 'calculation',
                      'valid', 'filter_reason', 'note']

def output_csv(race: dict, verbose: bool = False) -> str:
    out       = io.StringIO()
    start     = race['start']
    start_str = fmt_time(start) if start else ''
    fields    = CSV_FIELDS_VERBOSE if verbose else CSV_FIELDS_BRIEF
    writer    = csv.DictWriter(out, fieldnames=fields, lineterminator='\n')
    writer.writeheader()

    events = sorted(race['events'], key=lambda e: (int(e['lane']), lane_sort_key(e)))
    if not verbose:
        events = [ev for ev in events if is_keeper(ev)]

    for ev in events:
        elapsed = fmt_elapsed(ev['elapsed']) if ev['elapsed'] is not None else ''
        row = {'start_time': start_str, 'lane': ev['lane'],
               'event_type': ev['event_type'], 'elapsed_s': elapsed}
        if verbose:
            row.update({
                'start_source':  race['start_source'],
                'log_race_num':  ev['log_race_num'],
                'wall_time':     fmt_time(ev['wall_time']),
                'calculation':   f"{fmt_time(ev['wall_time'])} - {start_str}" if ev['elapsed'] is not None else '',
                'valid':         ev['valid'],
                'filter_reason': ev['filter_reason'] or '',
                'note':          'race number not set (embedded=0.00)' if not ev['valid'] else '',
            })
        writer.writerow(row)

    return out.getvalue()


# ── Output: Markdown ──────────────────────────────────────────────────────────

def output_markdown(race: dict, verbose: bool = False) -> str:
    out       = io.StringIO()
    start     = race['start']
    start_str = fmt_time(start) if start else ''

    if start:
        out.write(f"**Start signal:** `{start_str}`")
        if verbose:
            out.write(f"  \n**Source:** {race['start_source']}")
        out.write('\n\n')
    else:
        out.write(f"**Start signal:** NOT FOUND\n\n")

    if not race['events']:
        out.write("_No lane events found._\n")
        return out.getvalue()

    if verbose:
        out.write("| Lane | Event | Wall Time | Elapsed (s) | Calculation | Valid | Filtered | Note |\n")
        out.write("|-----:|-------|-----------|------------:|-------------|-------|----------|------|\n")
    else:
        out.write("| Lane | Event | Elapsed (s) |\n")
        out.write("|-----:|-------|------------:|\n")

    events = sorted(race['events'], key=lambda e: (int(e['lane']), lane_sort_key(e)))
    if not verbose:
        events = [ev for ev in events if is_keeper(ev)]

    for ev in events:
        elapsed = fmt_elapsed(ev['elapsed']) if ev['elapsed'] is not None else 'N/A'
        if verbose:
            calc     = f"`{fmt_time(ev['wall_time'])} - {start_str}`" if ev['elapsed'] is not None else ''
            valid    = 'Yes' if ev['valid'] else '**No**'
            filtered = ev['filter_reason'] or ''
            note     = 'race number not set' if not ev['valid'] else ''
            out.write(
                f"| {ev['lane']} | {ev['event_type']} | `{fmt_time(ev['wall_time'])}` "
                f"| {elapsed} | {calc} | {valid} | {filtered} | {note} |\n"
            )
        else:
            out.write(f"| {ev['lane']} | {ev['event_type']} | {elapsed} |\n")

    out.write('\n')
    return out.getvalue()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Parse Daktronics Omnisport 2000 timing logs.'
    )
    parser.add_argument('logfile', help='Path to the timing log file')
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument('--csv',      action='store_true', help='Output as CSV')
    fmt_group.add_argument('--markdown', action='store_true', help='Output as Markdown')
    parser.add_argument('-o', '--output', help='Write output to file instead of stdout')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show all events (INVALID, FILTERED) with wall-clock calculations')
    parser.add_argument(
        '--arm-delay', type=float, default=10.0, metavar='SECONDS',
        help='Discard touchpad events within this many seconds of the start signal '
             '(pre-arm window). Also discard any touchpad after the first valid one. '
             'Default: 10.0. Set to 0 to disable.',
    )
    args = parser.parse_args()

    race = parse_log(args.logfile)
    if not race['events'] and race['start'] is None:
        print("No race data found.", file=sys.stderr)
        sys.exit(1)

    if args.arm_delay > 0:
        apply_touchpad_filter(race, args.arm_delay)

    if args.csv:
        result = output_csv(race, verbose=args.verbose)
    elif args.markdown:
        result = output_markdown(race, verbose=args.verbose)
    else:
        result = output_console(race, verbose=args.verbose)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(result)
        print(f"Written to {args.output}")
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
