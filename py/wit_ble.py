#!/usr/bin/env python3
"""
WitMotion WT901BLE / WT9011 BLE streamer.

Connects to the sensor by MAC, subscribes to the notify characteristic,
parses 0x55 0x61 (acc+gyro+angle, 20 bytes) frames and prints decoded data.
"""
import asyncio
import struct
import sys
from bleak import BleakClient, BleakScanner

DEFAULT_MAC = "E3:A5:E2:DC:32:56"  # WT901BLE67 found in scan

# WitMotion BLE characteristics (common across WT901BLE / WT9011DCL)
NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
WRITE_UUID  = "0000ffe9-0000-1000-8000-00805f9a34fb"

ACC_SCALE   = 16.0   # g
GYRO_SCALE  = 2000.0 # deg/s
ANGLE_SCALE = 180.0  # deg

def parse_frame(buf: bytes):
    """Parse one 20-byte 0x55 0x61 frame -> dict."""
    if len(buf) < 20 or buf[0] != 0x55 or buf[1] != 0x61:
        return None
    ax, ay, az, wx, wy, wz, rx, ry, rz = struct.unpack_from("<9h", buf, 2)
    return {
        "ax": ax / 32768.0 * ACC_SCALE,
        "ay": ay / 32768.0 * ACC_SCALE,
        "az": az / 32768.0 * ACC_SCALE,
        "wx": wx / 32768.0 * GYRO_SCALE,
        "wy": wy / 32768.0 * GYRO_SCALE,
        "wz": wz / 32768.0 * GYRO_SCALE,
        "roll":  rx / 32768.0 * ANGLE_SCALE,
        "pitch": ry / 32768.0 * ANGLE_SCALE,
        "yaw":   rz / 32768.0 * ANGLE_SCALE,
    }

async def main(mac: str, n_samples: int):
    print(f"Scanning for {mac} ...", flush=True)
    device = await BleakScanner.find_device_by_address(mac, timeout=20.0)
    if device is None:
        print("Device not found in scan. Is it advertising? Try waking it up.")
        return
    print(f"Found {device.name} ({device.address}). Connecting ...", flush=True)
    async with BleakClient(device, timeout=20.0) as client:
        print("Connected. Services:")
        for s in client.services:
            print(f"  {s.uuid}")
            for c in s.characteristics:
                print(f"    char {c.uuid} props={c.properties}")
        count = 0
        done = asyncio.Event()
        buf = bytearray()

        def handler(_sender, data: bytearray):
            nonlocal count
            buf.extend(data)
            # consume frames
            while len(buf) >= 20:
                if buf[0] != 0x55:
                    del buf[0]
                    continue
                if len(buf) < 20:
                    break
                if buf[1] != 0x61:
                    del buf[0]
                    continue
                frame = bytes(buf[:20])
                del buf[:20]
                d = parse_frame(frame)
                if d is None:
                    continue
                count += 1
                print(f"#{count:4d} acc=({d['ax']:+.3f},{d['ay']:+.3f},{d['az']:+.3f})g "
                      f"gyro=({d['wx']:+7.2f},{d['wy']:+7.2f},{d['wz']:+7.2f})deg/s "
                      f"angle=(r={d['roll']:+7.2f},p={d['pitch']:+7.2f},y={d['yaw']:+7.2f})deg",
                      flush=True)
                if count >= n_samples:
                    done.set()
                    return

        await client.start_notify(NOTIFY_UUID, handler)
        try:
            await asyncio.wait_for(done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print("(timeout waiting for samples)")
        await client.stop_notify(NOTIFY_UUID)

if __name__ == "__main__":
    mac = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAC
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    asyncio.run(main(mac, n))
