# TRIsecure — Secure Multi-Factor eVoting System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-86%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-81%25-green.svg)](#testing)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%204%20ARM64-orange.svg)](https://www.raspberrypi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**TRIsecure** is a production-grade, embedded electronic voting terminal for Raspberry Pi 4 that enforces three-factor authentication — NFC smart card, live face biometric, and one-time session token — before recording a vote to a cryptographically hash-chained ledger.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Security Architecture](#security-architecture)
3. [Hardware Requirements](#hardware-requirements)
4. [Software Architecture](#software-architecture)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Usage](#usage)
8. [Deployment](#deployment)
9. [Testing](#testing)
10. [Database Schema](#database-schema)
11. [Performance](#performance)

---

## System Overview

TRIsecure addresses the core challenges of secure electronic voting in low-resource, offline environments:

| Challenge | Solution |
|-----------|----------|
| Voter impersonation | NFC card UID + MobileFaceNet biometric (cosine similarity ≥ 0.55) |
| Double voting | Atomic `has_voted` flag + session-token one-time use |
| Vote tampering | SHA-256 hash chain with optional HMAC-SHA256 per-vote signing |
| Biometric duplication | Aadhaar-style cross-registration check at enrollment |
| Data at rest | AES-256-GCM encrypted face embeddings (PBKDF2-HMAC-SHA256, 100k iterations) |
| NFC relay | AES-128-GCM HKDF-derived payload written directly to NTAG2xx user memory |
| Audit | Append-only `audit_events` table with structured event types |

### Voting Flow

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                     AUTHENTICATION PIPELINE                     │
  │                                                                 │
  │  [Voter] ──NFC tap──► [PN532 SPI] ──UID──► Voter lookup (DB)   │
  │                                               │                  │
  │                              ┌────────────── has_voted?         │
  │                              ▼                                   │
  │          [Webcam] ──frame──► Haar cascade ──► MobileFaceNet     │
  │                                               │                  │
  │                              cosine sim ≥ threshold?            │
  │                              │                                   │
  │                              ▼                                   │
  │              Session token (60s, one-time)                      │
  │                              │                                   │
  │                              ▼                                   │
  │              Ballot selection ──► Vote → SHA-256 chain          │
  └─────────────────────────────────────────────────────────────────┘
```

---

## Security Architecture

### Multi-Factor Authentication

**Factor 1 — NFC Smart Card**
- PN532 module reads passive ISO14443A card UID over SPI
- Voter UUID encrypted with AES-128-GCM (HKDF-SHA256 derived key) and written to NTAG2xx user memory (pages 4–19)
- Card mismatch during enrollment write triggers hard rejection

**Factor 2 — Face Biometric (MobileFaceNet)**
- Haar cascade (OpenCV) for real-time face detection
- MobileFaceNet ONNX model produces 512-D L2-normalized embeddings (CPU inference)
- Multi-template matching: enrollment captures 3 samples, voting matches best-of-N
- Biometric deduplication at enrollment rejects faces matching any existing voter (cosine ≥ 0.68)
- Embeddings stored encrypted: AES-256-GCM with per-embedding random salt + IV, PBKDF2 key derivation

**Factor 3 — One-Time Session Token**
- `secrets.token_urlsafe(32)` issued after NFC + face pass
- 60-second expiry; marked `used=True` immediately on consumption
- Rate limiter: 5 failures per 5-minute window per NFC UID

### Vote Integrity — Hash Chain

```
Genesis:   previous_hash = "0" × 64

Vote₀:     data = candidate‖timestamp‖previous_hash
           current_hash = SHA-256(data)

Vote₁:     previous_hash = Vote₀.current_hash
           current_hash = SHA-256(candidate‖timestamp‖Vote₁.previous_hash)
           vote_hmac = HMAC-SHA256(vote_id‖voter_id‖candidate‖timestamp‖prev_hash)
   ⋮
```

Any field modification breaks both the hash at that position **and** all subsequent hashes. The HMAC binding covers the voter identity, making silent substitution infeasible.

### Cryptographic Primitives

| Component | Algorithm | Key Size | Notes |
|-----------|-----------|----------|-------|
| Face embedding storage | AES-256-GCM | 256-bit | PBKDF2-HMAC-SHA256, 100k iter, random salt+IV per record |
| NFC payload | AES-128-GCM | 128-bit | HKDF-SHA256 from `TRISECURE_NFC_SECRET` |
| Vote chain | SHA-256 | — | Each vote hashes candidate + timestamp + prev_hash |
| Vote signing | HMAC-SHA256 | 256-bit | Optional; enabled when `TRISECURE_VOTE_SIGNING_KEY` is set |
| Audit integrity | HMAC-SHA256 | 256-bit | Optional; enabled when `TRISECURE_AUDIT_HMAC_KEY` is set |
| Session token | CSPRNG | 256-bit | `secrets.token_urlsafe(32)` |

---

## Hardware Requirements

| Component | Specification |
|-----------|---------------|
| SBC | Raspberry Pi 4 (4 GB RAM recommended) |
| OS | Ubuntu 22.04 LTS ARM64 (or Raspberry Pi OS 64-bit) |
| NFC Reader | PN532 module, SPI interface (CS=D8, RESET=D25) |
| Camera | USB webcam at `/dev/video0` (≥ 320×240 @ 15 fps) |
| Storage | ≥ 8 GB microSD or USB SSD |

**SPI wiring (PN532 ↔ Raspberry Pi 4):**

```
PN532 VCC  → Pi 3.3V (pin 1)
PN532 GND  → Pi GND  (pin 6)
PN532 SCK  → Pi SCK  (pin 23)
PN532 MISO → Pi MISO (pin 21)
PN532 MOSI → Pi MOSI (pin 19)
PN532 SS   → Pi CE0  (pin 24, GPIO8 / D8)
PN532 RST  → Pi GPIO25 (pin 22 / D25)
```

---

## Software Architecture

```
TriSecure/
├── app.py                     # Entry point — TRIsecureApp interactive terminal
├── config.py                  # Environment-aware configuration (dataclass + env vars)
│
├── models/                    # Pure domain entities (no I/O)
│   ├── voter.py               # Voter — id, name, nfc_uid, face_embedding, has_voted
│   ├── vote.py                # Vote — hash chain fields, HMAC signing
│   ├── session.py             # Session — one-time token, 60s expiry
│   └── audit_event.py        # AuditEvent — structured event log entries
│
├── repositories/              # SQLite persistence (repository pattern)
│   ├── voter_repository.py    # SQLiteVoterRepository — AES-256-GCM embedding storage
│   ├── vote_repository.py     # SQLiteVoteRepository — append-only hash chain + HMAC
│   └── audit_repository.py   # SQLiteAuditRepository — structured audit trail
│
├── core/                      # Business logic (no hardware dependencies)
│   ├── auth_pipeline.py       # AuthenticationPipeline — 5-stage MFA + rate limiter
│   ├── session_manager.py     # SessionManager — CSPRNG tokens, one-time use
│   └── audit_logger.py        # AuditLogger — structured event emission
│
├── hardware/
│   ├── camera/
│   │   ├── face_auth.py       # FaceCamera (capture) + FaceAuthenticator (MobileFaceNet)
│   │   └── face_service.py    # Higher-level face service wrapper
│   └── nfc/
│       ├── nfc_service.py     # NFCService — PN532 SPI read/write + AES-GCM NFC crypto
│       └── nfc_logger.py      # Diagnostic NFC tap logger
│
├── security/
│   └── blockchain_logger.py   # BlockchainLogger — hash chain operations + statistics
│
├── backend/
│   └── crypto/
│       └── encryptor.py       # EmbeddingEncryptor — AES-256-GCM with PBKDF2 key derivation
│
├── use_cases/                 # Clean-architecture use-case objects (CLI-injectable)
│   ├── enroll.py              # EnrollUseCase
│   ├── vote.py                # CastVoteUseCase
│   ├── verify.py              # VerifyFaceUseCase
│   ├── reenroll.py            # ReenrollUseCase
│   └── _face_helpers.py       # Shared face capture / template helpers
│
├── cli/
│   └── menu.py                # TRIsecureMenu — pure I/O dispatch, zero business logic
│
├── tests/                     # pytest test suite (86 tests, 81% coverage on core)
├── data/                      # Runtime data (DB, models, logs — gitignored)
│   └── face_models/           # Per-voter .npz template files
│
├── requirements.txt           # Python dependencies
├── Makefile                   # install / test / coverage / lint / run / backup
└── trisecure.service          # systemd unit file
```

### Dependency Rule

```
  hardware  →  core  →  models
  use_cases →  core  →  models
  app.py    →  everything
  (never: models → repositories, core → hardware)
```

---

## Installation

### 1. System dependencies

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3-dev python3-venv \
    i2c-tools libatlas-base-dev libhdf5-dev \
    libharfbuzz0b libwebp-dev v4l-utils
```

### 2. Enable SPI

```bash
sudo raspi-config   # Interface Options → SPI → Enable
# or add "dtparam=spi=on" to /boot/config.txt and reboot
```

### 3. Clone and install

```bash
git clone https://github.com/your-org/TRIsecure.git
cd TRIsecure
make install        # creates venv + installs requirements.txt
```

### 4. Verify hardware

```bash
# NFC (SPI device should appear)
ls /dev/spidev0.*

# Camera
v4l2-ctl --list-devices

# Test NFC in simulation mode
venv/bin/python -c "from hardware.nfc.nfc_service import NFCService; s=NFCService(); print(s.initialize())"
```

---

## Configuration

All settings are controlled via **`TRISECURE_*` environment variables**. The system reads them at startup with sensible defaults for development.

| Variable | Default | Description |
|----------|---------|-------------|
| `TRISECURE_MODE` | `development` | `development` / `staging` / `production` |
| `TRISECURE_DATABASE_PATH` | `data/trisecure.db` | SQLite database file path |
| `TRISECURE_NFC_TIMEOUT` | `5.0` | Seconds to wait for NFC card |
| `TRISECURE_BIOMETRIC_SIMILARITY_THRESHOLD` | `0.55` | Face cosine similarity threshold |
| `TRISECURE_MASTER_KEY` | *(required in prod)* | AES master key for embedding encryption |
| `TRISECURE_VOTE_SIGNING_KEY` | *(required in prod)* | HMAC key for per-vote signing |
| `TRISECURE_NFC_SECRET` | *(required in prod)* | AES key for NFC payload encryption |
| `TRISECURE_AUDIT_HMAC_KEY` | *(required in prod)* | HMAC key for audit log integrity |
| `TRISECURE_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

In **production mode** the system refuses to start if any of the four cryptographic keys are missing.

### Example production `.env`

```bash
TRISECURE_MODE=production
TRISECURE_DATABASE_PATH=/var/lib/trisecure/votes.db
TRISECURE_LOG_FILE=/var/log/trisecure/trisecure.log
TRISECURE_MASTER_KEY=<64-char hex key>
TRISECURE_VOTE_SIGNING_KEY=<64-char hex key>
TRISECURE_NFC_SECRET=<32-char hex key>
TRISECURE_AUDIT_HMAC_KEY=<64-char hex key>
```

---

## Usage

```bash
# Development (simulation mode — no hardware required)
make run

# With custom candidates
venv/bin/python app.py --candidates "Alice,Bob,Charlie"

# With custom face threshold
venv/bin/python app.py --threshold 0.60

# With specific webcam device
venv/bin/python app.py --device 1
```

### Terminal Menu

```
╔══════════════════════════════════════════════════════════╗
║         TRIsecure — Secure eVoting Terminal              ║
║   Face Recognition  ·  NFC Auth  ·  Blockchain Ledger   ║
╚══════════════════════════════════════════════════════════╝

  ────────────────────────────
   1  Enroll voter        (NFC + webcam face)
   2  Cast vote           (NFC + face match + ballot)
   3  Identify face       (webcam live identification)
   4  Statistics          (voters / votes / integrity)
   5  Re-enroll face      (update face template)
   0  Exit
  ────────────────────────────
```

**Option 1 — Enroll voter**
1. Scan NFC card → read UID
2. Webcam captures 3 face samples → averaged + normalized MobileFaceNet embedding
3. Biometric deduplication check against all enrolled voters
4. Voter record saved to SQLite (embedding encrypted with AES-256-GCM)
5. Encrypted voter UUID written back to NFC card (card must be re-tapped to confirm)

**Option 2 — Cast vote**
1. NFC scan → voter lookup → eligibility check
2. Live face capture → cosine similarity against stored template(s)
3. Ballot selection with confirmation prompt
4. Vote appended to SHA-256 hash chain; `has_voted` atomically set

---

## Deployment

### systemd service

```bash
# Install
sudo cp trisecure.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trisecure
sudo systemctl start trisecure

# Monitor
sudo journalctl -u trisecure -f

# Status
sudo systemctl status trisecure
```

The service runs as a dedicated `trisecure` user. Set the cryptographic keys in `/etc/trisecure.env` (mode 0600, owned by `trisecure`).

### Database backup

```bash
make backup   # creates data/backup_YYYYMMDD_HHMMSS.db
```

---

## Testing

```bash
# Run all tests
make test

# With coverage report (terminal)
make coverage

# With HTML coverage report
venv/bin/python -m pytest tests/ --cov=models --cov=core --cov=repositories \
    --cov=security --cov=config --cov=backend/crypto \
    --cov-report=html

# Type checking
make lint
```

### Test suite summary

| Module | Tests | Coverage |
|--------|-------|----------|
| `models/` | 22 | 97% |
| `core/` | 14 | 86% |
| `repositories/` | 25 | 76% |
| `security/blockchain_logger` | 9 | 82% |
| `backend/crypto/encryptor` | 5 | 75% |
| **Total** | **86** | **81%** |

Hardware-dependent modules (`hardware/camera/`, `hardware/nfc/`) require physical devices; they fall back to simulation mode in CI.

---

## Database Schema

### `voters`

```sql
CREATE TABLE voters (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    nfc_uid     TEXT UNIQUE NOT NULL,
    face_embedding  BLOB,           -- legacy plaintext (NULL when encrypted)
    face_enc_blob   BLOB,           -- AES-256-GCM ciphertext
    face_enc_salt   BLOB,           -- PBKDF2 salt (16 bytes)
    face_enc_iv     BLOB,           -- GCM IV (12 bytes)
    has_voted   INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX idx_voters_nfc_uid ON voters(nfc_uid);
```

### `votes` (append-only)

```sql
CREATE TABLE votes (
    sequence        INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id         TEXT NOT NULL UNIQUE,
    voter_id        TEXT NOT NULL,
    candidate       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    previous_hash   TEXT NOT NULL,  -- SHA-256 of previous vote (or 64 × "0")
    current_hash    TEXT NOT NULL,  -- SHA-256(candidate‖timestamp‖previous_hash)
    vote_hmac       TEXT            -- HMAC-SHA256 (NULL when signing disabled)
);
```

### `audit_events`

```sql
CREATE TABLE audit_events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,   -- see EventType enum
    voter_id    TEXT,
    timestamp   TEXT NOT NULL,
    status      TEXT NOT NULL,   -- SUCCESS / FAILURE / WARNING
    message     TEXT NOT NULL,
    details     TEXT             -- JSON blob
);
CREATE INDEX idx_audit_events_voter    ON audit_events(voter_id);
CREATE INDEX idx_audit_events_type     ON audit_events(event_type);
CREATE INDEX idx_audit_events_timestamp ON audit_events(timestamp DESC);
```

---

## Performance

Measured on Raspberry Pi 4 (4 GB, Raspberry Pi OS 64-bit, Python 3.11):

| Operation | Median latency |
|-----------|---------------|
| NFC card read (hardware) | ~120 ms |
| Face detection (Haar cascade, 320×240) | ~45 ms/frame |
| MobileFaceNet embedding (ONNX CPU) | ~180 ms |
| Cosine similarity (512-D, 10 templates) | < 1 ms |
| SQLite voter lookup (indexed) | < 5 ms |
| Vote append + hash chain | < 10 ms |
| AES-256-GCM encrypt embedding | ~8 ms |
| Full enroll flow (3 samples) | ~3 s |
| Full vote flow (1 sample) | ~2 s |

End-to-end authentication (NFC tap → face verification → session token) typically completes in **under 5 seconds** under normal lighting.

---

## Troubleshooting

**NFC not detected**
```bash
ls /dev/spidev0.*          # should show spidev0.0
python -c "import board"   # verify adafruit-blinka is installed
```

**Camera not found**
```bash
ls /dev/video*             # e.g. /dev/video0
v4l2-ctl --list-devices
python app.py --device 1   # try a different index
```

**Face threshold too strict / too loose**
- Lower threshold (e.g. `--threshold 0.45`) reduces false rejections at cost of security
- Raise threshold (e.g. `--threshold 0.65`) for stricter identity verification
- Default `0.55` is tuned for MobileFaceNet cosine similarity on 320×240 captures

**Database integrity check**
```bash
sqlite3 data/trisecure.db "PRAGMA integrity_check;"
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

## Authors

Vivek Reddy — TRIsecure eVoting System
