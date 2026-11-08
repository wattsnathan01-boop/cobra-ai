"""System info: CPU, memory, temperatures, battery, GPU."""
from __future__ import annotations

import asyncio
import shutil

import psutil

from . import sh, tool


@tool("system_stats",
      "Current CPU load, memory use, temperatures, battery and NVIDIA GPU status.",
      permission="always")
async def system_stats() -> dict:
    mem = psutil.virtual_memory()
    stats: dict = {
        # measuring takes 0.3 s; do it off the event loop so audio and the overlay keep flowing
        "cpu_percent": await asyncio.to_thread(psutil.cpu_percent, 0.3),
        "memory_used_gb": round(mem.used / 2**30, 1),
        "memory_total_gb": round(mem.total / 2**30, 1),
    }

    temps = getattr(psutil, "sensors_temperatures", lambda: {})()
    cpu = temps.get("coretemp") or temps.get("k10temp") or []
    if cpu:
        stats["cpu_temp_c"] = round(max(s.current for s in cpu))

    battery = psutil.sensors_battery()
    if battery:
        stats["battery_percent"] = round(battery.percent)
        stats["charging"] = battery.power_plugged

    if shutil.which("nvidia-smi"):
        out = await sh("nvidia-smi",
                       "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                       "--format=csv,noheader,nounits")
        name, temp, util, used, total = [x.strip() for x in out.splitlines()[0].split(",")]
        stats["gpu"] = {"name": name, "temp_c": int(temp), "load_percent": int(util),
                        "vram_used_mb": int(used), "vram_total_mb": int(total)}
    return stats
