#!/usr/bin/env python3
"""
Write LOWPOWER (register 0x25) on a WitMotion WT901BLE.

Protocol per WitMotion docs (5-byte config writes to 0xFFE9):
  FF AA 69 88 B5     unlock
  FF AA 25 LO HI     set reg 0x25 = HI:LO
  FF AA 00 00 00     save to flash

Reads back 0x25 before and after so we can verify.

Usage:  .venv/bin/python wit_write_lowpower.py [value_seconds] [MAC]
Default value is 3600 (1 hour) — conservative choice if "0 = disabled"
turns out to mean "0 = sleep immediately".
"""
import asyncio
import struct
import sys
from bleak import BleakClient, BleakScanner

DEFAULT_MAC   = "E3:A5:E2:DC:32:56"
DEFAULT_VALUE = 3600
NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
WRITE_UUID  = "0000ffe9-0000-1000-8000-00805f9a34fb"
LOWPOWER_REG = 0x25


async def read_reg(client, write_uuid, base_reg, response_event, latest):
    latest.clear()
    response_event.clear()
    cmd = bytes([0xFF, 0xAA, 0x27, base_reg, 0x00])
    await client.write_gatt_char(write_uuid, cmd, response=False)
    await asyncio.wait_for(response_event.wait(), timeout=2.0)
    frame = latest[-1]
    values = struct.unpack_from("<8H", frame, 4)
    return values  # 8 consecutive regs starting at base_reg


async def main(value: int, mac: str):
    if not (0 <= value <= 0xFFFF):
        print(f"Value {value} out of u16 range 0..65535")
        return 1

    print(f"Scanning for {mac} ...", flush=True)
    device = await BleakScanner.find_device_by_address(mac, timeout=20.0)
    if device is None:
        print("Device not advertising. Power-cycle to wake.")
        return 1
    print(f"Found {device.name} ({device.address}). Connecting ...", flush=True)

    async with BleakClient(device, timeout=20.0) as client:
        print("Connected.", flush=True)

        # Frame parser identical to wit_regs.py
        buf = bytearray()
        latest = []
        response_event = asyncio.Event()

        def handler(_sender, data: bytearray):
            buf.extend(data)
            while len(buf) >= 20:
                if buf[0] != 0x55:
                    del buf[0]
                    continue
                if len(buf) < 20:
                    break
                hdr = buf[1]
                frame = bytes(buf[:20])
                del buf[:20]
                if hdr == 0x71:
                    latest.append(frame)
                    response_event.set()

        await client.start_notify(NOTIFY_UUID, handler)

        # Read BEFORE
        before = await read_reg(client, WRITE_UUID, LOWPOWER_REG, response_event, latest)
        print(f"\nBEFORE: reg 0x{LOWPOWER_REG:02X} = 0x{before[0]:04X} ({before[0]})")
        print(f"         neighbours 0x{LOWPOWER_REG:02X}..0x{LOWPOWER_REG+7:02X}: "
              f"{[hex(v) for v in before]}")

        # Confirm we're about to change something
        print(f"\nWill write reg 0x{LOWPOWER_REG:02X} = 0x{value:04X} ({value} seconds)")

        # 1. Unlock
        unlock = bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5])
        print(f"  → unlock: {unlock.hex()}")
        await client.write_gatt_char(WRITE_UUID, unlock, response=False)
        await asyncio.sleep(0.2)  # tiny delay: WitMotion docs recommend brief pause after unlock

        # 2. Write
        lo, hi = value & 0xFF, (value >> 8) & 0xFF
        write_cmd = bytes([0xFF, 0xAA, LOWPOWER_REG, lo, hi])
        print(f"  → write:  {write_cmd.hex()}")
        await client.write_gatt_char(WRITE_UUID, write_cmd, response=False)
        await asyncio.sleep(0.2)

        # 3. Save to flash
        save = bytes([0xFF, 0xAA, 0x00, 0x00, 0x00])
        print(f"  → save:   {save.hex()}")
        await client.write_gatt_char(WRITE_UUID, save, response=False)
        await asyncio.sleep(0.5)  # flash write needs a moment

        # Read AFTER
        after = await read_reg(client, WRITE_UUID, LOWPOWER_REG, response_event, latest)
        print(f"\nAFTER:  reg 0x{LOWPOWER_REG:02X} = 0x{after[0]:04X} ({after[0]})")
        print(f"         neighbours 0x{LOWPOWER_REG:02X}..0x{LOWPOWER_REG+7:02X}: "
              f"{[hex(v) for v in after]}")

        if after[0] == value:
            print(f"\n✓ Write confirmed: 0x{LOWPOWER_REG:02X} = {value}")
        else:
            print(f"\n✗ Write did NOT stick: expected {value}, got {after[0]}")

        await client.stop_notify(NOTIFY_UUID)

    return 0


if __name__ == "__main__":
    value = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VALUE
    mac   = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MAC
    sys.exit(asyncio.run(main(value, mac)) or 0)
