import asyncio
from bleak import BleakScanner
async def main():
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    for d, adv in sorted(found.values(), key=lambda x: -x[1].rssi):
        print(d.address, adv.rssi, repr(adv.local_name), adv.service_uuids, {k: v.hex() for k, v in adv.manufacturer_data.items()})
asyncio.run(main())
