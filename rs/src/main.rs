use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, CharPropFlags};
use btleplug::platform::Manager;
use futures::StreamExt;
use std::time::Duration;
use uuid::Uuid;

const TARGET_MAC: &str = "E3:A5:E2:DC:32:56";
const NOTIFY_UUID: Uuid = Uuid::from_u128(0x0000ffe4_0000_1000_8000_00805f9a34fb);

const ACC_SCALE: f32 = 16.0;
const GYRO_SCALE: f32 = 2000.0;
const ANGLE_SCALE: f32 = 180.0;

fn parse_frame(buf: &[u8]) -> Option<[f32; 9]> {
    if buf.len() < 20 || buf[0] != 0x55 || buf[1] != 0x61 {
        return None;
    }
    let mut v = [0i16; 9];
    for i in 0..9 {
        let lo = buf[2 + i * 2] as u16;
        let hi = buf[3 + i * 2] as u16;
        v[i] = ((hi << 8) | lo) as i16;
    }
    Some([
        v[0] as f32 / 32768.0 * ACC_SCALE,
        v[1] as f32 / 32768.0 * ACC_SCALE,
        v[2] as f32 / 32768.0 * ACC_SCALE,
        v[3] as f32 / 32768.0 * GYRO_SCALE,
        v[4] as f32 / 32768.0 * GYRO_SCALE,
        v[5] as f32 / 32768.0 * GYRO_SCALE,
        v[6] as f32 / 32768.0 * ANGLE_SCALE,
        v[7] as f32 / 32768.0 * ANGLE_SCALE,
        v[8] as f32 / 32768.0 * ANGLE_SCALE,
    ])
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manager = Manager::new().await?;
    let adapters = manager.adapters().await?;
    let central = adapters.into_iter().next().ok_or("no BLE adapter")?;

    println!("Scanning ...");
    central.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs(6)).await;

    let mut target = None;
    for p in central.peripherals().await? {
        let addr = p.address().to_string().to_uppercase();
        if addr == TARGET_MAC {
            target = Some(p);
            break;
        }
    }
    let p = target.ok_or("target not found in scan")?;
    let _ = central.stop_scan().await;

    let props = p.properties().await?.unwrap();
    println!("Found {:?} ({})", props.local_name, p.address());
    p.connect().await?;
    p.discover_services().await?;

    let mut notify_char = None;
    for c in p.characteristics() {
        if c.uuid == NOTIFY_UUID && c.properties.contains(CharPropFlags::NOTIFY) {
            notify_char = Some(c);
            break;
        }
    }
    let nc = notify_char.ok_or("notify char not found")?;
    p.subscribe(&nc).await?;

    let mut notifications = p.notifications().await?;
    let mut buf: Vec<u8> = Vec::with_capacity(64);
    let mut count = 0usize;
    let max = 20;
    while let Some(n) = notifications.next().await {
        buf.extend_from_slice(&n.value);
        loop {
            // Find a 0x55 start
            while !buf.is_empty() && buf[0] != 0x55 {
                buf.remove(0);
            }
            if buf.len() < 20 {
                break;
            }
            if buf[1] != 0x61 {
                buf.remove(0);
                continue;
            }
            let frame: Vec<u8> = buf.drain(..20).collect();
            if let Some(d) = parse_frame(&frame) {
                count += 1;
                println!(
                    "#{:4} acc=({:+.3},{:+.3},{:+.3})g gyro=({:+7.2},{:+7.2},{:+7.2})deg/s angle=(r={:+7.2},p={:+7.2},y={:+7.2})deg",
                    count, d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]
                );
                if count >= max {
                    break;
                }
            }
        }
        if count >= max {
            break;
        }
    }
    let _ = p.unsubscribe(&nc).await;
    let _ = p.disconnect().await;
    Ok(())
}
