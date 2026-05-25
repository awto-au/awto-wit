#!/usr/bin/env python3
"""
Read WitMotion BLE config registers without modifying anything.

Sends `FF AA 27 <reg> 00` for each register of interest and prints the
8-register block that comes back as a `55 5F` frame.

Usage:  .venv/bin/python wit_regs.py [MAC]
"""
import asyncio
import struct
import sys
from bleak import BleakClient, BleakScanner

DEFAULT_MAC = "E3:A5:E2:DC:32:56"
NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
WRITE_UUID  = "0000ffe9-0000-1000-8000-00805f9a34fb"

# Registers we want to read (each read returns 8 consecutive regs)
READ_REGS = [
    (0x00, "SAVE..CALSW area"),
    (0x03, "RRATE — output data rate"),
    (0x10, "0x10..0x17 — calibration area"),
    (0x18, "0x18..0x1F — gyro/orient flags"),
    (0x20, "0x20..0x27 — power/sleep area (incl. neighbours of LOWPOWER)"),
    (0x28, "0x28..0x2F — continue after LOWPOWER"),
    (0x30, "0x30..0x37 — orient/calib"),
    (0x38, "0x38..0x3F"),
    (0x60, "0x60..0x67 — MAC mirror + version"),
    (0x68, "0x68..0x6F"),
    (0x70, "0x70..0x77"),
    (0x78, "0x78..0x7F"),
]

# Known register names for the 8-reg blocks (best-effort labels)
REG_NAMES = {
    0x00: "SAVE", 0x01: "CALSW", 0x02: "RSW", 0x03: "RRATE",
    0x04: "BAUD", 0x05: "AXOFFSET", 0x06: "AYOFFSET", 0x07: "AZOFFSET",
    0x08: "GXOFFSET", 0x09: "GYOFFSET", 0x0A: "GZOFFSET",
    0x0B: "HXOFFSET", 0x0C: "HYOFFSET", 0x0D: "HZOFFSET",
    0x0F: "UNLOCK_ECHO", 0x69: "UNLOCK",
    0x22: "SLEEP", 0x23: "ORIENT", 0x24: "POWERONSEND", 0x25: "LOWPOWER",
    0x63: "BANDWIDTH",
}


async def main(mac: str):
    print(f"Scanning for {mac} ...", flush=True)
    device = await BleakScanner.find_device_by_address(mac, timeout=20.0)
    if device is None:
        print("Device not found in scan. Is it advertising? Try waking it up.")
        return 1
    print(f"Found {device.name} ({device.address}). Connecting ...", flush=True)

    async with BleakClient(device, timeout=20.0) as client:
        print("Connected.", flush=True)

        # Stream of notification chunks may carry many `55 ??` frames packed
        # back-to-back, and a single frame can be split across two notifications.
        # We accumulate into a buffer and pull out 20-byte frames as they arrive.
        buf = bytearray()
        latest_response: list[bytes] = []
        notify_count = [0]
        response_arrived = asyncio.Event()

        def handler(_sender, data: bytearray):
            notify_count[0] += 1
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
                if hdr == 0x71:  # register-read response (this firmware)
                    latest_response.append(frame)
                    response_arrived.set()
                elif hdr == 0x61:
                    pass  # data frame, ignore
                else:
                    print(f"  [unknown frame header 0x55 0x{hdr:02X}: {frame.hex()}]")

        await client.start_notify(NOTIFY_UUID, handler)

        # Quick passive listen first to confirm notifications are flowing
        print("\nPassive listen for 2s to see what's streaming...")
        await asyncio.sleep(2.0)
        print(f"  Got {notify_count[0]} notifications, {len(latest_response)} register-read frames.")
        notify_count[0] = 0
        latest_response.clear()

        try:
            for reg, desc in READ_REGS:
                latest_response.clear()
                response_arrived.clear()
                cmd = bytes([0xFF, 0xAA, 0x27, reg, 0x00])
                print(f"\n→ read register 0x{reg:02X}  ({desc})", flush=True)
                await client.write_gatt_char(WRITE_UUID, cmd, response=False)
                try:
                    await asyncio.wait_for(response_arrived.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    print(f"  (no response within 2s)")
                    continue

                frame = latest_response[-1]
                # Frame layout: 55 71 <reg> 00 <8 × u16 LE = 16 bytes>
                resp_reg = frame[2]
                if resp_reg != reg:
                    print(f"  [warning: asked 0x{reg:02X}, got response for 0x{resp_reg:02X}]")
                values = struct.unpack_from("<8H", frame, 4)
                for i, v in enumerate(values):
                    r = resp_reg + i
                    name = REG_NAMES.get(r, "?")
                    print(f"  reg 0x{r:02X} ({name:14s}) = 0x{v:04X}  ({v})")
        finally:
            await client.stop_notify(NOTIFY_UUID)

    return 0


if __name__ == "__main__":
    mac = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAC
    sys.exit(asyncio.run(main(mac)) or 0)
