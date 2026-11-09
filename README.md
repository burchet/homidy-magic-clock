# goofy-clock

Control the **Homidy Magical Goofy MG001** sunrise alarm clock over Bluetooth LE
from Python, without the vendor app. Includes NTP time sync and a documented
protocol.

The clock has an RGB globe light, a sound player with 30 built-in sounds, an
LED display, four sunrise alarms, a focus timer and time-window light schedules.

## Usage

```sh
make deps            # create venv, install bleak + ntplib
make                 # sync clock time from pool.ntp.org
make dump            # read and decode all settings
```

```sh
.venv/bin/python goofy.py light ff8800 40       # custom RGB, brightness 0-100
.venv/bin/python goofy.py light sunrise 80      # sunrise | loop | off
.venv/bin/python goofy.py volume rain 30        # play a sound, 0 stops
.venv/bin/python goofy.py screen 3              # display brightness 1-7
.venv/bin/python goofy.py alarm 0:06:45 15      # slot 0, 15 min sunrise lead
.venv/bin/python goofy.py alarm 0:off
.venv/bin/python goofy.py focus 25              # focus timer, minutes
.venv/bin/python goofy.py focus stop
.venv/bin/python goofy.py format 24             # 12 | 24
.venv/bin/python goofy.py holiday on            # on | off
.venv/bin/python goofy.py raw <hex>             # send any frame
```

Any getter name works as a command too, e.g. `time`, `battery`, `version`,
`status`, `alarm`, `schedules`, `focus`.

`scan.py` lists nearby BLE devices, `gatt.py` dumps the GATT table.

Tested on macOS with firmware `MGL_S0.6.3`. Should work on Linux and Windows via
[bleak](https://github.com/hbldh/bleak).

## Device

| | |
|---|---|
| Advertised name | `MI Goofy GL-xxxx` (last 4 hex digits of the BLE address) |
| Chip | JieLi (manufacturer data reads `JLAISDK`) |
| Control channel | service `0000ae30-…`, characteristic `0000ae10-…` (write + notify) |
| Pairing | none, no bonding, no key |

Services `ae00` and `ae3a` belong to the JieLi RCSP stack (firmware update).
Don't write to them unless you know what you're doing.

## Frame format

All traffic uses characteristic `ae10`. Write with response, subscribe to notify.

```
request:  BB len 00 00 00 00 00 01 01 cmd payload… 00 AA
response: BB len <6-byte device id>  00 cmd payload… 00 AA
```

* `len` is the total frame length including `BB` and `AA`.
* The byte before `AA` is a checksum slot. The clock ignores it; send `00`.
* The header must be exactly `00×5 01 01`. A shifted frame is parsed as cmd `01`.
* Read commands are the set command plus `0x70` (set time `04`, read time `74`).
* The clock acks setters by echoing `cmd 00` and pushes state changes on its
  own, e.g. a `73` light update after any light change.
* On macOS every notification arrives twice.

Example, set time to 2026-11-09 10:50:58:

```
BB 13 00 00 00 00 00 01 01 04 07 EA 0B 09 0A 32 3A 00 AA
```

## Commands

| Set | Read | Feature | Payload | Status |
|---|---|---|---|---|
| `00` | `70` | Alarms, 4 slots | 16 bytes per slot, see below | works |
| `01` | `71` | Sound player | sound id, volume 0-100 (0 stops) | works |
| `02` | `72` | Display brightness | on, level 1-7 (0 is clamped to 1) | works |
| `03` | `73` | Globe light | mode, R, G, B, brightness 0-100 | works |
| `04` | `74` | Time | year (2 bytes BE), month, day, hour, min, sec | works |
| `05`/`06` | `75` | Countdown start / cancel | `01 01` minutes (2 bytes) | no reply |
| `07` | `77` | Classic BT speaker | 00/01 | no visible effect |
| `08` | `78` | Snooze setting | 00/01 | ack only |
| `09` | `79` | Time format | 00 = 12 h, 01 = 24 h | works |
| – | `7F` | Battery | percent | works |
| `80` | `81` | Light/sound running | 00/01 | read works |
| `82` | `83` | Key lock | 00/01 | unclear |
| `84` | – | Alarm preview | sound, volume, R, G, B, brightness | works |
| `85` | – | Stop alarm sound | – | silences, alarm still snoozes |
| – | `86` | Classic BT address | 6 bytes | works |
| – | `87` | Firmware version | ASCII | works |
| – | `88` | Status word | 2 bytes, see below | works |
| `89` | – | Alarm now | 00/01 | ack only |
| `90` | `91` | Favourite scene | light, sound, timer | no reply |
| `92` | `93` | Endurance mode | 00/01 | read works |
| `94` | `95` | Alarm master switch | 00/01 | works |
| `96` | `97` | Holiday mode | 00/01 | works |
| `B0` | `B1` | Schedule master switch | 00/01 | read works |
| `B2` | `B3` | Light schedules | 13 bytes each | read works |
| `B4` | `B5` | Focus presets | 10 bytes each | read works |
| `B6` | – | Start focus timer | 11 bytes | works |
| `B7` | – | Stop focus timer | – | works |

"no reply" means firmware `MGL_S0.6.3` ignores the command.

### Light (`03`)

| Mode | Meaning |
|---|---|
| `01` | red `ff0000` |
| `02` | `ff2100` |
| `03` | orange `ff8800` |
| `04` | green `00ff00` |
| `05` | cyan `00ffff` |
| `06` | blue `0000ff` |
| `07` | pink `ff00c6` |
| `08` | colour loop |
| `09` | rose `ff0039` |
| `0A` | custom RGB from payload |
| `0B` | off |
| `0C` | sunrise |

Presets ignore the RGB bytes and report their own colour back in `73`.

### Alarm slot (`00`, 16 bytes)

```
slot  days  on  hour  min  sound  vol  snz_n  snz_min  snz_n  snz_min  lead  R G B  bright
```

* `days`: bit 6 = Monday … bit 0 = Sunday, `7F` = every day.
* `lead`: minutes of sunrise light before the alarm. RGB `000000` = sunrise ramp.
* The clock rewrites the snooze bytes to `06 09 06 09` (6 × 9 min).
* Sunrise ramp goes dark → red → lavender → full white, then the display blinks
  while ringing.
* There is no remote dismiss. `85` stops the sound but the alarm keeps snoozing
  every 9 minutes; rewriting the slot doesn't end a running snooze. Press the
  button on the clock.

### Schedule (`B2`, 13 bytes each)

```
state  days  start_h  start_m  end_h  end_m  sound  vol  mode  bright  R G B
```

`state`: bit 0 = on, bit 1 = locked. Frame `len` = 12 + 13 × count.

### Focus timer (`B6`, 11 bytes) and presets (`B4`/`B5`, 10 bytes each)

```
B6: on  hours  min  sound  vol  mode  bright  R G B  lock
B5: hours  min  sound  vol  mode  bright  R G B  lock
```

The display counts down while the timer runs.

### Status word (`88`)

Byte 1, bits from LSB:

| Bit | Meaning |
|---|---|
| 0 | classic Bluetooth on |
| 1 | sound playing |
| 2 | charging |
| 3 | alarm active (ringing or snoozed) |
| 4 | snooze |
| 7 | lock |

Byte 2: `00` none, `01` LED, `04` BLE connected, `05` BLE + LED.

### Display icons

The left icon shows an armed alarm, the mark right of the minutes shows an
active BLE connection.

### Sounds (`01`, alarms, schedules, focus)

| Id | Sound | Id | Sound | Id | Sound |
|---|---|---|---|---|---|
| `10` | Bird | `22` | Water flow | `3A` | Baby marimba |
| `11` | Cicada | `23` | Fountain | `41` | Clock |
| `12` | Cricket | `25` | Rain | `44` | White noise |
| `14` | Wind in trees | `26` | Rain on puddle | `45` | Brown noise |
| `15` | Frog | `28` | Ocean | `46` | Pink noise |
| `16` | Seagull | `29` | Sea | `50` | One fine day |
| `17` | Winds | `2C` | Waves | `51` | Canon |
| `18` | Forest | `31` | Brahms lullaby | `52` | Alarm ring |
| `1A` | First light | `32` | Indian drums | `53` | Radar |
| `1D` | Winter | `33` | Rattle | `FF` | Mute |

## License

MIT
