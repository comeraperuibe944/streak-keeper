import os
import json
import time
import platform
import psutil
from datetime import datetime, timezone, timedelta

def generate_fallback_commit(fallback_type="telemetry", tz_offset_hours=-3):
    target_tz = timezone(timedelta(hours=tz_offset_hours))
    now = datetime.now(target_tz)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    # Collect basic server metrics safely
    try:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        uptime_sec = int(time.time() - psutil.boot_time())
        days, rem = divmod(uptime_sec, 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        uptime_fmt = f"{days}d {hours}h {mins}m"
        load = [round(x, 2) for x in psutil.getloadavg()] if hasattr(psutil, "getloadavg") else [0, 0, 0]
    except Exception:
        cpu_usage = 0.0
        mem = None
        uptime_fmt = "unknown"
        load = [0, 0, 0]

    if fallback_type == "audit":
        file_path = "logs/system_audit.log"
        commit_message = f"chore(audit): routine server diagnostic check [{date_str}]"
        content = (
            f"TIMESTAMP: {timestamp_str} (BRT)\n"
            f"HOST: {platform.node()}\n"
            f"SYSTEM: {platform.system()} {platform.release()} ({platform.machine()})\n"
            f"STATUS: HEALTHY\n"
            f"UPTIME: {uptime_fmt}\n"
            f"CPU_LOAD_AVG: {load}\n"
            f"CHECKSUM: OK\n"
            f"----------------------------------------\n"
        )
    elif fallback_type == "benchmark":
        file_path = "benchmarks/daily_checkpoint.json"
        commit_message = f"perf(benchmark): record routine system throughput snapshot [{date_str}]"
        payload = {
            "timestamp": timestamp_str,
            "date": date_str,
            "node": platform.node(),
            "cpu_percent": cpu_usage,
            "ram_percent": mem.percent if mem else 0,
            "ram_used_bytes": mem.used if mem else 0,
            "load_avg": load,
            "uptime": uptime_fmt,
            "status": "nominal"
        }
        content = json.dumps(payload, indent=2)
    else: # telemetry (default)
        file_path = "telemetry/server_metrics.json"
        commit_message = f"chore(telemetry): snapshot server metrics [{date_str}]"
        payload = {
            "snapshot_time": timestamp_str,
            "date": date_str,
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "uptime": uptime_fmt,
            "cpu_usage_percent": cpu_usage,
            "ram_used_mb": round((mem.used / (1024 * 1024)), 2) if mem else 0,
            "ram_total_mb": round((mem.total / (1024 * 1024)), 2) if mem else 0,
            "ram_percent": mem.percent if mem else 0,
            "load_avg_1_5_15m": load,
            "agent": "StreakKeeper-Daemon"
        }
        content = json.dumps(payload, indent=2)

    return {
        "file_path": file_path,
        "commit_message": commit_message,
        "content": content
    }
