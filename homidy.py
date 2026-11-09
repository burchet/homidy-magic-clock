#!/usr/bin/env python3
"""Homidy Magic Clock (MG001) BLE client."""
import argparse
import asyncio
import datetime as dt

import ntplib
from bleak import BleakClient, BleakScanner

NAME = "MI Goofy"
SVC = "0000ae30-0000-1000-8000-00805f9b34fb"
CHR = "0000ae10-0000-1000-8000-00805f9b34fb"

# getter commands
GETTERS = {
    "alarm": 0x70, "volume": 0x71, "screen": 0x72, "light": 0x73,
    "time": 0x74, "countdown": 0x75, "bt": 0x77, "snooze": 0x78,
    "format": 0x79, "battery": 0x7F, "switch": 0x81, "lock": 0x83,
    "btaddr": 0x86, "version": 0x87, "status": 0x88, "favorite": 0x91,
    "endurance": 0x93, "alarmswitch": 0x95, "holiday": 0x97,
    "program": 0xB1, "schedules": 0xB3, "focus": 0xB5,
}

# status byte bits, lsb first
STATUS_BITS = ["bt", "sound", "charging", "alarm", "snooze", "b5", "b6", "lock"]
DAYS = "MoTuWeThFrSaSu"


def frame(cmd, payload=b""):
    # BB len 00x5 01 01 cmd payload crc(0) AA
    body = bytes(5) + b"\x01\x01" + bytes([cmd]) + payload
    return bytes([0xBB, len(body) + 4]) + body + b"\x00\xAA"


def time_frame(t):
    return frame(0x04, t.year.to_bytes(2, "big") + bytes(
        [t.month, t.day, t.hour, t.minute, t.second]))


LIGHT_MODES = {"sunrise": 0x0C, "loop": 0x08, "off": 0x0B}

SOUNDS = {
    "mute": "ff", "firstlight": "1a", "bird": "10", "puddle": "26",
    "cricket": "12", "lullaby": "31", "onefineday": "50", "waves": "2c",
    "wind": "14", "ocean": "28", "fountain": "23", "rattle": "33",
    "canon": "51", "waterflow": "22", "drums": "32", "brown": "45",
    "marimba": "3a", "clock": "41", "alarm": "52", "sea": "29",
    "forest": "18", "frog": "15", "winds": "17", "white": "44",
    "radar": "53", "winter": "1d", "seagull": "16", "pink": "46",
    "rain": "25", "cicada": "11",
}


def light_mode(color):
    # preset name or rrggbb
    if color in LIGHT_MODES:
        return LIGHT_MODES[color], bytes(3)
    return 0x0A, bytes.fromhex(color.lstrip("#"))


def light_frame(color, level):
    # mode, rgb, brightness 0-100
    mode, rgb = light_mode(color)
    return frame(0x03, bytes([mode]) + rgb + bytes([level]))


def schedule_entry(span, color="sunrise", bright=50, mask=0x7F):
    # span = HH:MM-HH:MM, light only
    (h1, m1), (h2, m2) = (map(int, t.split(":")) for t in span.split("-"))
    mode, rgb = light_mode(color)
    return bytes([1, mask, h1, m1, h2, m2, 0xFF, 50, mode, bright]) + rgb


def parse(data):
    if len(data) < 12 or data[0] != 0xBB:
        return f"raw {data.hex()}"
    mac = data[2:8].hex(":")
    cmd, p = data[9], data[10:-2]
    if cmd == 0x74 and len(p) >= 7:
        y = int.from_bytes(p[:2], "big")
        return f"time {y:04}-{p[2]:02}-{p[3]:02} {p[4]:02}:{p[5]:02}:{p[6]:02}"
    if cmd == 0x7F:
        return f"battery {p[0]}%"
    if cmd == 0x87:
        return f"version {p.decode(errors='replace')}"
    if cmd == 0x88:
        bits = [n for i, n in enumerate(STATUS_BITS) if p[0] >> i & 1]
        return f"status {','.join(bits)} ble={'on' if p[1] & 4 else 'off'}"
    if cmd == 0x73:
        return f"light mode {p[0]:02x} rgb {p[1:4].hex()} bright {p[4]}"
    if cmd == 0x71:
        return f"sound {p[0]:02x} vol {p[1]}"
    if cmd == 0x70:
        return "alarms " + " | ".join(
            f"#{e[0]} {'on' if e[2] else 'off'} {e[3]:02}:{e[4]:02} {days(e[1])} "
            f"snd {e[5]:02x} vol {e[6]} pre {e[11]}m rgb {e[12:15].hex()} br {e[15]}"
            for e in chunks(p, 16))
    if cmd == 0xB3:
        return "schedules " + " | ".join(
            f"{e[2]:02}:{e[3]:02}-{e[4]:02}:{e[5]:02} {days(e[1])} st {e[0]} "
            f"snd {e[6]:02x} vol {e[7]} mode {e[8]:02x} br {e[9]} rgb {e[10:13].hex()}"
            for e in chunks(p, 13))
    if cmd == 0xB5:
        return "focus " + " | ".join(
            f"{e[0]}h{e[1]:02}m snd {e[2]:02x} vol {e[3]} mode {e[4]:02x} br {e[5]}"
            for e in chunks(p, 10))
    return f"cmd {cmd:02x} mac {mac} payload {p.hex()}"


def chunks(p, n):
    return [p[i:i + n] for i in range(0, len(p) - n + 1, n)]


def days(mask):
    # bit6 = Monday ... bit0 = Sunday
    return "".join(DAYS[2 * i:2 * i + 2] if mask >> (6 - i) & 1 else ".." for i in range(7))


def alarm_frame(slot, hhmm, on=True, sound="firstlight", vol=40, pre=10, mask=0x7F):
    # pre = sunrise minutes before alarm
    h, m = map(int, hhmm.split(":"))
    sid = int(SOUNDS.get(sound, sound), 16)
    return frame(0x00, bytes([slot, mask, int(on), h, m, sid, vol,
                              3, 9, 1, 9, pre, 0, 0, 0, 80]))


def focus_frame(minutes, sound="rain", vol=30, rgb="ff8800", bright=50):
    sid = int(SOUNDS.get(sound, sound), 16)
    return frame(0xB6, bytes([1, minutes // 60, minutes % 60, sid, vol, 0x0A, bright])
                 + bytes.fromhex(rgb) + b"\x00")


def ntp_now():
    try:
        r = ntplib.NTPClient().request("pool.ntp.org", version=3, timeout=3)
        off = r.offset
    except Exception as e:
        print(f"NTP failed, using system clock: {e}")
        off = 0.0
    now = dt.datetime.now() + dt.timedelta(seconds=off)
    return now, off


async def run(args):
    dev = await BleakScanner.find_device_by_filter(
        lambda d, a: (a.local_name or d.name or "").startswith(NAME), timeout=15)
    if not dev:
        raise SystemExit("Clock not found")
    async with BleakClient(dev) as c:
        last = {}

        def on_data(_, d):
            print("<", d.hex(), "|", parse(d))
            if len(d) >= 12:
                last[d[9]] = bytes(d[10:-2])

        await c.start_notify(CHR, on_data)

        async def send(data):
            print(">", data.hex())
            await c.write_gatt_char(CHR, data, response=True)
            await asyncio.sleep(0.8)

        if args.cmd == "sync":
            now, off = ntp_now()
            # wait for next full second
            await asyncio.sleep(1 - now.microsecond / 1e6)
            now = (now + dt.timedelta(seconds=1)).replace(microsecond=0)
            print(f"NTP offset {off:+.3f}s, setting {now}")
            await send(time_frame(now))
            await send(frame(0x74))
        elif args.cmd == "light" and args.arg:
            await send(light_frame(args.arg, args.level))
            await send(frame(0x73))
        elif args.cmd == "volume" and args.arg:
            sid = SOUNDS.get(args.arg, args.arg)
            await send(frame(0x01, bytes([int(sid, 16), args.level])))
        elif args.cmd == "screen" and args.arg:
            # level 1-7, 0 is ignored
            lvl = max(1, min(7, int(args.arg)))
            await send(frame(0x02, bytes([1, lvl])))
        elif args.cmd == "alarm" and args.arg:
            # arg = slot:HH:MM or slot:off
            slot, rest = args.arg.split(":", 1)
            on = rest != "off"
            await send(alarm_frame(int(slot), rest if on else "08:00", on, pre=args.level))
            await send(frame(0x70))
        elif args.cmd == "focus" and args.arg:
            if args.arg == "stop":
                await send(frame(0xB7))
            else:
                await send(focus_frame(int(args.arg)))
        elif args.cmd == "schedule" and args.arg:
            if args.arg in ("on", "off"):
                await send(frame(0xB0, bytes([args.arg == "on"])))
                await send(frame(0xB1))
            else:
                await send(frame(0xB3))
                rows = chunks(last.get(0xB3, b""), 13)
                if args.arg == "clear":
                    rows = []
                elif args.arg.startswith("del:"):
                    rows.pop(int(args.arg[4:]) - 1)
                else:
                    span, _, color = args.arg.partition(",")
                    rows.append(schedule_entry(span, color or "sunrise", args.level))
                await send(frame(0xB2, b"".join(rows)))
        elif args.cmd == "format" and args.arg:
            await send(frame(0x09, bytes([args.arg == "24"])))
        elif args.cmd == "holiday" and args.arg:
            await send(frame(0x96, bytes([args.arg == "on"])))
        elif args.cmd == "raw":
            await send(bytes.fromhex(args.arg))
        elif args.cmd == "dump":
            for cmd in GETTERS.values():
                await send(frame(cmd))
        else:
            await send(frame(GETTERS[args.cmd]))
        await asyncio.sleep(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["sync", "raw", "dump", "schedule", *GETTERS])
    ap.add_argument("arg", nargs="?", help=(
        "raw: hex frame; light: rrggbb|sunrise|loop|off; "
        "volume: sound name; screen: 1-7; alarm: slot:HH:MM|slot:off; "
        "focus: minutes|stop; "
        "schedule: on|off|clear|del:N|HH:MM-HH:MM[,rrggbb|sunrise|loop]; format: 12|24; holiday: on|off"))
    ap.add_argument("level", nargs="?", type=int, default=50,
                    help="brightness, volume 0-100, or alarm sunrise minutes")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
