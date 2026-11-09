import asyncio, sys
from bleak import BleakClient, BleakScanner
NAME = "MI Goofy"
async def main():
    dev = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or "").startswith(NAME), timeout=15)
    async with BleakClient(dev) as c:
        for s in c.services:
            print("S", s.uuid, s.description)
            for ch in s.characteristics:
                val = ""
                if "read" in ch.properties:
                    try: val = (await c.read_gatt_char(ch)).hex()
                    except Exception as e: val = f"err {e}"
                print("  C", ch.uuid, ch.properties, val)
asyncio.run(main())
