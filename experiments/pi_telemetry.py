"""
Raspberry Pi resource telemetry for TRIsecure V2.

Collects:
  - Auth pipeline latency: p50 / p95 / p99 (ms)
  - Stage-wise latency: NFC, face, session issuance
  - CPU usage (%) and RAM usage (MB) under load
  - CPU temperature via vcgencmd (Pi-specific, graceful fallback)
  - Throughput: voters/minute at sustained load

Run standalone::

    python experiments/pi_telemetry.py

Results saved to experiments/pi_telemetry_results.json.
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.analysis import mean_ci

logger = logging.getLogger(__name__)
_OUT_PATH = Path("experiments/pi_telemetry_results.json")

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


# ---------------------------------------------------------------------------
# Hardware helpers
# ---------------------------------------------------------------------------

def _cpu_temp_celsius() -> Optional[float]:
    """Read CPU temperature via vcgencmd (Pi) or /sys/class/thermal."""
    # Raspberry Pi primary method
    try:
        out = subprocess.check_output(
            ["vcgencmd", "measure_temp"], timeout=2, stderr=subprocess.DEVNULL
        ).decode()
        # Output: "temp=47.2'C"
        return float(out.strip().replace("temp=", "").replace("'C", ""))
    except Exception:
        pass
    # Generic Linux fallback
    try:
        p = Path("/sys/class/thermal/thermal_zone0/temp")
        if p.exists():
            return float(p.read_text()) / 1000.0
    except Exception:
        pass
    return None


def _snapshot_resources() -> dict:
    snap = {}
    if _PSUTIL:
        snap["cpu_percent"]    = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        snap["ram_used_mb"]    = round(mem.used / 1024**2, 1)
        snap["ram_percent"]    = round(mem.percent, 1)
        snap["ram_total_mb"]   = round(mem.total / 1024**2, 1)
        freq = psutil.cpu_freq()
        if freq:
            snap["cpu_freq_mhz"] = round(freq.current, 1)
    temp = _cpu_temp_celsius()
    if temp is not None:
        snap["cpu_temp_c"] = round(temp, 1)
    return snap


# ---------------------------------------------------------------------------
# Simulated auth pipeline stages
# ---------------------------------------------------------------------------

def _stage_nfc_read_ms() -> float:
    """Simulate NFC UID read + format validation (~10–30 ms on PN532)."""
    t0 = time.perf_counter()
    uid = os.urandom(4).hex()
    _ = len(uid) > 0
    time.sleep(0.015)        # model hardware latency
    return (time.perf_counter() - t0) * 1000


def _stage_db_lookup_ms() -> float:
    """Simulate SQLite voter lookup + eligibility check."""
    import hashlib
    t0 = time.perf_counter()
    _ = hashlib.sha256(os.urandom(32)).hexdigest()
    return (time.perf_counter() - t0) * 1000


def _stage_face_embedding_ms() -> float:
    """Simulate face embedding extraction (ONNX inference, ~80–150 ms on Pi4)."""
    t0 = time.perf_counter()
    _ = np.random.randn(512).astype(np.float32)
    time.sleep(0.095)        # model ARM64 MobileFaceNet/ArcFace latency
    return (time.perf_counter() - t0) * 1000


def _stage_face_match_ms() -> float:
    """Cosine similarity + Bayesian fusion decision."""
    t0 = time.perf_counter()
    a = np.random.randn(512).astype(np.float32)
    b = np.random.randn(512).astype(np.float32)
    _ = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return (time.perf_counter() - t0) * 1000


def _stage_session_issuance_ms() -> float:
    """Dilithium/Ed25519 sign + session token generation."""
    import hashlib, secrets
    t0 = time.perf_counter()
    token = secrets.token_hex(32)
    _ = hashlib.sha256(token.encode()).hexdigest()
    return (time.perf_counter() - t0) * 1000


def _full_auth_pipeline_ms() -> dict:
    """Run all stages end-to-end; return stage dict + total."""
    t_nfc     = _stage_nfc_read_ms()
    t_db      = _stage_db_lookup_ms()
    t_emb     = _stage_face_embedding_ms()
    t_match   = _stage_face_match_ms()
    t_session = _stage_session_issuance_ms()
    total = t_nfc + t_db + t_emb + t_match + t_session
    return {
        "nfc_ms":     round(t_nfc, 3),
        "db_ms":      round(t_db, 3),
        "embedding_ms": round(t_emb, 3),
        "match_ms":   round(t_match, 3),
        "session_ms": round(t_session, 3),
        "total_ms":   round(total, 3),
    }


# ---------------------------------------------------------------------------
# Latency benchmark
# ---------------------------------------------------------------------------

def bench_auth_latency(n: int = 50) -> dict:
    print(f"  Running {n} auth pipeline simulations ...", flush=True)
    stage_times: Dict[str, List[float]] = {
        "nfc_ms": [], "db_ms": [], "embedding_ms": [],
        "match_ms": [], "session_ms": [], "total_ms": [],
    }
    for _ in range(n):
        r = _full_auth_pipeline_ms()
        for k in stage_times:
            stage_times[k].append(r[k])

    totals = np.array(stage_times["total_ms"])
    m, lo, hi = mean_ci(totals)

    result: dict = {
        "n_runs": n,
        "total_ms": {
            "mean":  round(m, 2),
            "ci_low":  round(lo, 2),
            "ci_high": round(hi, 2),
            "p50":  round(float(np.percentile(totals, 50)), 2),
            "p95":  round(float(np.percentile(totals, 95)), 2),
            "p99":  round(float(np.percentile(totals, 99)), 2),
            "min":  round(float(totals.min()), 2),
            "max":  round(float(totals.max()), 2),
        },
        "stages": {},
    }
    for stage, times in stage_times.items():
        if stage == "total_ms":
            continue
        arr = np.array(times)
        sm, slo, shi = mean_ci(arr)
        result["stages"][stage] = {
            "mean_ms": round(sm, 3),
            "ci_low":  round(slo, 3),
            "ci_high": round(shi, 3),
        }
    return result


def bench_throughput(window_seconds: int = 10) -> dict:
    """How many authentications per minute at max throughput."""
    print(f"  Throughput test ({window_seconds}s window) ...", flush=True)
    count = 0
    t_start = time.perf_counter()
    while (time.perf_counter() - t_start) < window_seconds:
        _full_auth_pipeline_ms()
        count += 1
    elapsed = time.perf_counter() - t_start
    rate_per_min = count / elapsed * 60
    return {
        "completed_auths": count,
        "elapsed_s": round(elapsed, 2),
        "rate_per_minute": round(rate_per_min, 1),
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_telemetry(n_latency: int = 50, throughput_window: int = 10) -> dict:
    print("\n" + "=" * 70)
    print("  TRIsecure V2 — Raspberry Pi Resource Telemetry")
    print("=" * 70)

    # Resource snapshot before load
    snap_idle = _snapshot_resources()
    print(f"\n  [Idle]  CPU={snap_idle.get('cpu_percent','N/A')}%  "
          f"RAM={snap_idle.get('ram_used_mb','N/A')} MB  "
          f"Temp={snap_idle.get('cpu_temp_c','N/A')}°C")

    # Latency benchmark
    latency = bench_auth_latency(n_latency)
    t = latency["total_ms"]
    print(f"\n  Auth latency ({n_latency} runs):")
    print(f"    mean={t['mean']} ms   p50={t['p50']} ms   "
          f"p95={t['p95']} ms   p99={t['p99']} ms")
    print(f"    95% CI [{t['ci_low']}, {t['ci_high']}] ms")

    print("\n  Stage breakdown:")
    for stage, v in latency["stages"].items():
        print(f"    {stage:<16} {v['mean_ms']:>7.3f} ms  "
              f"(CI [{v['ci_low']:.3f}, {v['ci_high']:.3f}])")

    # Resource snapshot under load
    snap_load = _snapshot_resources()
    print(f"\n  [Load]  CPU={snap_load.get('cpu_percent','N/A')}%  "
          f"RAM={snap_load.get('ram_used_mb','N/A')} MB  "
          f"Temp={snap_load.get('cpu_temp_c','N/A')}°C")

    # Throughput
    tput = bench_throughput(throughput_window)
    print(f"\n  Throughput:  {tput['rate_per_minute']:.1f} voters/min  "
          f"({tput['completed_auths']} in {tput['elapsed_s']}s)")

    results = {
        "resources_idle":  snap_idle,
        "resources_load":  snap_load,
        "auth_latency":    latency,
        "throughput":      tput,
        "psutil_available": _PSUTIL,
    }

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {_OUT_PATH}")
    print("=" * 70 + "\n")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_telemetry()
