# WIT investigation — sources & how to regenerate

The artifacts produced while reverse-engineering the **WT901BLE67 / BWT901BLE5.0**
are large (~900 MB total) and **regenerable**, so they are **not committed**.
Recreate any of them as below. The *findings* are in
[`ARCHITECTURE.md`](ARCHITECTURE.md) + issue #1 — that's the part worth keeping.

| Artifact | ~Size | Source / how to regenerate |
|---|---|---|
| **WitMotion PC software + manuals** | 508 M | Google Drive folder `1TLutidDBd_tDg5aTXgjvkz63OVt5_8ZZ` → `python -m gdown --folder <url> -O .` (contains `Standard Software for Windows PC.zip` = MiniIMU + the STM32-ISP updater). |
| **BWT901BLE5.0 SDK** (Android/iOS/Windows/Unity/Python) | 68 M | `git clone https://github.com/WITMOTION/WitBluetooth_BWT901BLE5_0` — the demo apps that *do* connect this non-CL unit. |
| **WitMotion app APK** (`com.wit.wit_app`) | ~13 M | Play Store; or `adb shell pm path com.wit.wit_app` then `adb pull` the split APKs (base + arm64 + en + dpi). |
| **Decompiled app** (Flutter Dart-AOT) | 106 M | `git clone https://github.com/worawit/blutter` → `python3 blutter.py <apk>/lib/arm64-v8a out/` (needs system `capstone`). `libapp.so` = Dart AOT; `libflutter.so` = engine. |
| **Vendor protocol docs / PDFs** | — | already in `docs/wit/` (awto-l8-app) — *WIT Standard Communication Protocol* etc. |
| **frida instrumentation** | — | `pip install frida-tools objection`; `objection patchapk` (note: needs `extractNativeLibs="true"` + gadget in `lib/arm64-v8a/`). Dev/RE only — never ship. |

## Key facts proven (no need to re-derive)
- `0x25` = **FILTK** (dynamic filtering), not LOWPOWER. Battery = reg **`0x5C` BATVAL**. Sleep = reg **`0x22`** (one-shot); no auto-sleep-timeout register.
- Architecture: **nRF52 + MPU9250**, single-MCU (nRF runs BLE + fusion + registers).
- **Firmware is not publicly distributed** — support-only.
- App: use the **`BWT901BLE5.0` SDK**, not the CL `com.wit.wit_app`.
- **Serial/debug console** (NUS `6E40…` / ISSC `49535343…`) is referenced by the app
  but **unconfirmed on this unit** — needs a live `--services` GATT dump (sensor awake).
