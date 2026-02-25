# TRIsecure - Production-Grade Secure eVoting System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![ARM64](https://img.shields.io/badge/platform-ARM64-orange.svg)](https://www.raspberrypi.com/)

**Secure Electronic Voting System for Raspberry Pi 4 + Ubuntu ARM64**

## Overview

TRIsecure is a **production-grade, modular, secure electronic voting system** designed specifically for Raspberry Pi 4 running Ubuntu 22.04 ARM64. The system implements clean architecture principles with multi-factor biometric authentication, blockchain-ready vote integrity, and full audit trails.

### Key Features

- **Multi-Factor Authentication**
  - NFC card verification (PN532 I2C reader)
  - Face recognition & biometric matching
  - Temporary session tokens (60-second expiry)
  - Strict one-time voting enforcement

- **Vote Integrity**
  - SHA256 hash chaining (blockchain-style)
  - Append-only vote ledger
  - Chain tamper detection
  - Cryptographic signatures (future)

- **Clean Architecture**
  - Domain-driven design with dataclass models
  - Dependency injection friendly
  - Hardware abstraction layer
  - Repository pattern for data persistence
  - Service layer for business logic

- **Production Ready**
  - Comprehensive audit logging
  - Structured Python logging
  - SQLite persistence with indices
  - Graceful error handling
  - Linux/Raspberry Pi optimized

- **Future Roadmap**
  - Blockchain integration (Ethereum/Hyperledger)
  - End-to-end encryption (OpenSSL/ChaCha20)
  - Distributed voter database
  - Web UI & REST API
  - Hardware security module (HSM) support

## Architecture

```
trisecure/
├── models/                 # Domain entities (Voter, Vote, Session, AuditEvent)
├── core/                   # Business logic (AuthenticationPipeline, SessionManager)
├── services/               # Hardware abstraction (NFC, Camera, Face)
├── repositories/           # Data persistence (Voter, Vote, Audit repositories)
├── security/               # Blockchain logger, Encryption hooks
├── infrastructure/         # Deployment utilities
├── config.py              # Environment-based configuration
├── main.py                # System entry point
└── __init__.py
```

## Hardware Requirements

- **Raspberry Pi 4** (4GB+ RAM recommended)
- **Ubuntu 22.04 LTS (ARM64)**
- **PN532 NFC Reader** (I2C interface, address 0x24)
- **USB Webcam** (/dev/video0)
- **I2C enabled** in raspi-config

## Installation

### 1. System Setup

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade

# Install Python and dependencies
sudo apt-get install python3.10 python3.10-dev python3.10-venv

# Install system libraries
sudo apt-get install i2c-tools libatlas-base-dev libjasper-dev libhdf5-dev
sudo apt-get install libqtgui4 libqt4-test libharfbuzz0b libwebp6

# Enable I2C (for NFC)
sudo raspi-config  # Interface > I2C > Enable
```

### 2. Clone and Setup

```bash
cd /opt/trisecure
git clone https://github.com/yourusername/trisecure.git .

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

### 3. Verify Hardware

```bash
# Check I2C devices
i2cdetect -y 1

# Output should show:
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- --
# 10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
# 20: -- -- -- -- 24 -- -- -- -- -- -- -- -- -- -- --  <- NFC at 0x24
```

## Usage

### Development Mode

```bash
# Run system (will execute example workflow)
python trisecure/main.py

# Output:
# ╔═══════════════════════════════════════════════════════════════════╗
# ║           TRISECURE - SECURE eVOTING SYSTEM v1.0                 ║
# ║      Raspberry Pi 4 + Ubuntu ARM + Face Recognition + NFC         ║
# ╚═══════════════════════════════════════════════════════════════════╝
```

### Production Deployment

#### Option 1: Systemd Service

```bash
# Install service
sudo cp trisecure.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trisecure
sudo systemctl start trisecure

# Monitor logs
sudo journalctl -u trisecure -f
```

#### Option 2: Manual Startup

```bash
source /opt/trisecure/venv/bin/activate
TRISECURE_MODE=production python trisecure/main.py
```

### Configuration

Configure via environment variables:

```bash
export TRISECURE_MODE=production
export TRISECURE_DATABASE_PATH=/var/lib/trisecure/votes.db
export TRISECURE_LOG_FILE=/var/log/trisecure/trisecure.log
export TRISECURE_NFC_ENABLED=true
export TRISECURE_FACE_MATCH_THRESHOLD=0.7
```

## API Examples

### Register Voter

```python
from trisecure import TRIsecureSystem

system = TRIsecureSystem()
system.initialize()

# Register new voter
voter = system.register_voter_workflow("John Doe")
# Prompts for:
# 1. NFC card scan
# 2. Face capture
# Returns: Voter object with ID, embedding stored
```

### Cast Vote

```python
# Voting workflow with multi-factor auth
success = system.voting_workflow("Candidate A")
# Flow:
# 1. NFC verification
# 2. Voter lookup
# 3. Eligibility check
# 4. Face matching
# 5. Session token issuance
# 6. Vote cast & recorded
# 7. Chain integrity maintained
```

### Verify Integrity

```python
# Verify vote blockchain is tamper-proof
valid = system.verify_vote_integrity()  # True/False

# View statistics
system.display_statistics()
# Output:
# Registered Voters: 100
# Voted: 87
# Eligible: 13
# Votes Cast: 87
# Blockchain Valid: ✓ Yes
# Chain Height: 87
```

## Security Architecture

### Authentication Pipeline

```
1. NFC Verification
   └─> Read NFC UID and validate format
   
2. Voter Lookup
   └─> Search voter by NFC UID
   
3. Eligibility Check
   └─> Verify voter hasn't already voted
   
4. Face Verification
   └─> Capture face
   └─> Generate 128-D embedding
   └─> Compare with stored embedding
   └─> Verify confidence > threshold
   
5. Session Issuance
   └─> Generate cryptographic token
   └─> Set 60-second expiry
   └─> One-time use enforced
```

### Vote Integrity

Each vote is linked via hash chain:

```
Vote Chain:
[Vote 0] → current_hash = SHA256("CandidateA" | "2024-01-15T10:30:00" | genesis)
    ↓
[Vote 1] → current_hash = SHA256("CandidateB" | "2024-01-15T10:31:00" | vote0.hash)
    ↓
[Vote 2] → current_hash = SHA256("CandidateC" | "2024-01-15T10:32:00" | vote1.hash)

If any vote is modified → chain breaks → integrity violation detected
```

### Audit Trail

Every system event is logged:

```
- VOTER_REGISTERED
- VOTER_NFC_REGISTERED
- VOTER_FACE_REGISTERED
- NFC_READ_SUCCESS / NFC_READ_FAILED
- VOTER_VERIFIED
- FACE_MATCH_SUCCESS / FACE_MATCH_FAILED
- SESSION_ISSUED
- VOTE_CAST
- VOTE_RECORDED
- SYSTEM_ERROR
- HARDWARE_ERROR
```

## Database Schema

### Voters Table

```sql
CREATE TABLE voters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    nfc_uid TEXT UNIQUE NOT NULL,
    face_embedding BLOB,
    has_voted INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_voters_nfc_uid ON voters(nfc_uid);
```

### Votes Table (Append-Only)

```sql
CREATE TABLE votes (
    vote_id TEXT PRIMARY KEY,
    voter_id TEXT NOT NULL,
    candidate TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL,
    sequence INTEGER
);
CREATE INDEX idx_votes_timestamp ON votes(timestamp);
```

### Audit Events Table

```sql
CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    voter_id TEXT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT
);
CREATE INDEX idx_audit_timestamp ON audit_events(timestamp DESC);
```

## Blockchain Integration Roadmap

### Phase 1 (Current) ✓
- Internal hash chaining
- Append-only vote ledger
- Chain verification

### Phase 2 (Q2 2024)
- Ethereum smart contract posting
- Vote hash storage on chain
- Off-chain/on-chain sync

### Phase 3 (Q3 2024)
- Hyperledger Fabric integration
- Distributed voter database
- Multi-site redundancy

### Phase 4 (Q4 2024)
- Hardware security module (HSM) support
- End-to-end encryption
- Web UI & REST API

## Testing

```bash
# Run tests
pytest tests/ -v

# Coverage report
pytest tests/ --cov=trisecure --cov-report=html

# Type checking
mypy trisecure/

# Linting
flake8 trisecure/
black --check trisecure/
```

## Troubleshooting

### NFC Not Detected

```bash
# Verify I2C is enabled
sudo raspi-config  # Interface > I2C > Enable

# Check device
i2cdetect -y 1

# Test with command line
python -c "import busio; import board; i2c = busio.I2C(board.SCL, board.SDA); print(i2c.scan())"
```

### Camera Issues

```bash
# Check camera device
ls -la /dev/video0

# Test with OpenCV
python -c "import cv2; cap = cv2.VideoCapture('/dev/video0'); print(cap.isOpened())"

# List all devices
v4l2-ctl --list-devices
```

### Face Recognition Slow

- On Raspberry Pi, use `FACE_MODEL="hog"` (default, faster)
- Avoid `FACE_MODEL="cnn"` (requires GPU)
- Reduce `FACE_JITTER` from 5 to 1 for faster but less robust matching

### Database Corruption

```bash
# Backup database
cp trisecure.db trisecure.db.backup

# Verify integrity
sqlite3 trisecure.db "PRAGMA integrity_check;"

# Rebuild indices if needed
sqlite3 trisecure.db ".rebuild"
```

## Development

### Code Style

```bash
# Format code
black trisecure/

# Sort imports
isort trisecure/

# Lint
flake8 trisecure/ --max-line-length=100
```

### Architecture Principles

1. **Clean Architecture**: Dependencies point inward to domain models
2. **SOLID Principles**: Single responsibility, open/closed, Liskov substitution, etc.
3. **Dependency Injection**: Services injected, not created
4. **Type Hints**: Full type coverage for IDE support and static analysis
5. **Separation of Concerns**: Hardware, business logic, persistence strictly separated

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/xyz`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push to branch (`git push origin feature/xyz`)
5. Create Pull Request

## License

MIT License - See [LICENSE](LICENSE) file for details

## Authors

- **Vivek** - Original development for TRIsecure eVoting System

## Support

- 📧 Email: support@trisecure.dev
- 📚 Documentation: https://trisecure.dev/docs
- 🐛 Issues: https://github.com/yourusername/trisecure/issues

## Disclaimer

This is a prototype system for demonstration purposes. For production election systems, consult with election security experts and comply with all applicable election laws and security standards.
