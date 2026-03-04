"""
Configuration management for TRIsecure eVoting system.

Environment-based configuration supporting:
- Raspberry Pi hardware settings
- Database paths
- Security parameters
- Logging configuration
- Deployment modes (development, staging, production)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class DeploymentMode(str, Enum):
    """System deployment modes."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class Config:
    """
    TRIsecure configuration.
    
    All values are environment-aware and can be overridden via
    environment variables for containerized/systemd deployment.
    """
    
    # Deployment
    MODE: DeploymentMode = DeploymentMode.DEVELOPMENT
    DEBUG: bool = False
    
    # Database
    DATABASE_PATH: str = "data/trisecure.db"
    DATABASE_BACKUP_PATH: str = "data/trisecure_backup.db"
    
    # NFC Hardware
    NFC_ENABLED: bool = True
    NFC_I2C_ADDRESS: int = 0x24
    NFC_I2C_BUS: int = 1
    NFC_TIMEOUT: float = 5.0
    
    # Camera Hardware
    CAMERA_ENABLED: bool = True
    CAMERA_DEVICE: str = "/dev/video0"
    CAMERA_WIDTH: int = 320
    CAMERA_HEIGHT: int = 240
    CAMERA_FPS: int = 15
    
    # Face Recognition
    FACE_ENABLED: bool = True
    FACE_MODEL: str = "hog"  # "hog" (fast) or "cnn" (accurate)
    FACE_JITTER: int = 1  # 1 for fast, 5+ for robust
    FACE_MATCH_THRESHOLD: float = 0.7
    FACE_ENCODING_TOLERANCE: float = 0.6
    
    # Biometric Authentication (MobileFaceNet pipeline)
    BIOMETRIC_ENABLED: bool = True
    BIOMETRIC_SIMILARITY_THRESHOLD: float = 0.55  # Cosine similarity (0.5-0.6 recommended)
    BIOMETRIC_DATABASE_PATH: str = "data/biometrics.db"
    BIOMETRIC_MODEL_PATH: str = ""  # Empty = auto-detect MobileFaceNet model
    BIOMETRIC_EMBEDDING_SIZE: int = 512  # MobileFaceNet output dimension
    
    # Session Management
    SESSION_DURATION_SECONDS: int = 60
    SESSION_CLEANUP_INTERVAL: int = 300  # 5 minutes
    
    # Security
    ENCRYPTION_ENABLED: bool = False  # Enable in Phase 2
    BLOCKCHAIN_ENABLED: bool = False  # Enable in Phase 2
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "data/trisecure.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5
    
    # Voting Configuration
    CANDIDATES: list = None  # Will be set to default list
    
    def __post_init__(self):
        """Load configuration from environment and set defaults."""
        self._load_from_environment()
        
        # Set default candidates if not provided
        if not self.CANDIDATES:
            self.CANDIDATES = ["Candidate A", "Candidate B", "Candidate C"]
    
    def _load_from_environment(self) -> None:
        """
        Load configuration overrides from environment variables.
        
        Environment variable naming: TRISECURE_{SETTING_NAME}
        Examples:
        - TRISECURE_MODE=production
        - TRISECURE_NFC_ENABLED=false
        - TRISECURE_DATABASE_PATH=/var/lib/trisecure/votes.db
        """
        env_prefix = "TRISECURE_"
        
        # Deployment
        mode_str = os.getenv(f"{env_prefix}MODE", self.MODE.value)
        try:
            self.MODE = DeploymentMode(mode_str)
        except ValueError:
            logging.warning(f"Invalid mode '{mode_str}', using {self.MODE.value}")
        
        self.DEBUG = self._parse_bool(os.getenv(f"{env_prefix}DEBUG"), self.DEBUG)
        
        # Database
        self.DATABASE_PATH = os.getenv(f"{env_prefix}DATABASE_PATH", self.DATABASE_PATH)
        self.DATABASE_BACKUP_PATH = os.getenv(f"{env_prefix}DATABASE_BACKUP_PATH", self.DATABASE_BACKUP_PATH)
        
        # NFC
        self.NFC_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}NFC_ENABLED"), self.NFC_ENABLED)

        # NFC_I2C_ADDRESS: allow hex strings like "0x24" but do not
        # pass an int into int(..., 0) (which raises TypeError).
        nfc_addr_str = os.getenv(f"{env_prefix}NFC_I2C_ADDRESS")
        if nfc_addr_str is not None:
            try:
                self.NFC_I2C_ADDRESS = int(nfc_addr_str, 0)
            except ValueError:
                logging.warning(
                    "Invalid NFC_I2C_ADDRESS '%s', keeping default 0x%X",
                    nfc_addr_str,
                    self.NFC_I2C_ADDRESS,
                )

        self.NFC_I2C_BUS = int(os.getenv(f"{env_prefix}NFC_I2C_BUS", str(self.NFC_I2C_BUS)))
        self.NFC_TIMEOUT = float(os.getenv(f"{env_prefix}NFC_TIMEOUT", str(self.NFC_TIMEOUT)))
        
        # Camera
        self.CAMERA_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}CAMERA_ENABLED"), self.CAMERA_ENABLED)
        self.CAMERA_DEVICE = os.getenv(f"{env_prefix}CAMERA_DEVICE", self.CAMERA_DEVICE)
        self.CAMERA_WIDTH = int(os.getenv(f"{env_prefix}CAMERA_WIDTH", self.CAMERA_WIDTH))
        self.CAMERA_HEIGHT = int(os.getenv(f"{env_prefix}CAMERA_HEIGHT", self.CAMERA_HEIGHT))
        self.CAMERA_FPS = int(os.getenv(f"{env_prefix}CAMERA_FPS", self.CAMERA_FPS))
        
        # Face
        self.FACE_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}FACE_ENABLED"), self.FACE_ENABLED)
        self.FACE_MODEL = os.getenv(f"{env_prefix}FACE_MODEL", self.FACE_MODEL)
        self.FACE_JITTER = int(os.getenv(f"{env_prefix}FACE_JITTER", self.FACE_JITTER))
        self.FACE_MATCH_THRESHOLD = float(os.getenv(f"{env_prefix}FACE_MATCH_THRESHOLD", self.FACE_MATCH_THRESHOLD))
        
        # Biometric Authentication
        self.BIOMETRIC_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}BIOMETRIC_ENABLED"), self.BIOMETRIC_ENABLED)
        self.BIOMETRIC_SIMILARITY_THRESHOLD = float(os.getenv(f"{env_prefix}BIOMETRIC_SIMILARITY_THRESHOLD", self.BIOMETRIC_SIMILARITY_THRESHOLD))
        self.BIOMETRIC_DATABASE_PATH = os.getenv(f"{env_prefix}BIOMETRIC_DATABASE_PATH", self.BIOMETRIC_DATABASE_PATH)
        self.BIOMETRIC_MODEL_PATH = os.getenv(f"{env_prefix}BIOMETRIC_MODEL_PATH", self.BIOMETRIC_MODEL_PATH)
        
        # Security
        self.ENCRYPTION_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}ENCRYPTION_ENABLED"), self.ENCRYPTION_ENABLED)
        self.BLOCKCHAIN_ENABLED = self._parse_bool(os.getenv(f"{env_prefix}BLOCKCHAIN_ENABLED"), self.BLOCKCHAIN_ENABLED)
        
        # Logging
        self.LOG_LEVEL = os.getenv(f"{env_prefix}LOG_LEVEL", self.LOG_LEVEL).upper()
        self.LOG_FILE = os.getenv(f"{env_prefix}LOG_FILE", self.LOG_FILE)
    
    @staticmethod
    def _parse_bool(value: Optional[str], default: bool) -> bool:
        """Parse boolean from string."""
        if value is None:
            return default
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.MODE == DeploymentMode.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.MODE == DeploymentMode.DEVELOPMENT


def setup_logging(config: Config) -> logging.Logger:
    """
    Configure logging for TRIsecure system.
    
    Features:
    - File rotation
    - Structured logging with timestamps
    - Console output in development
    - Syslog support (future)
    
    Args:
        config: Config object
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.LOG_LEVEL))
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler (development)
    if config.is_development():
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized - Mode: {config.MODE.value}, Level: {config.LOG_LEVEL}")
    return logger


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get global configuration instance (singleton pattern).
    
    Returns:
        Config object
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def initialize_config(mode: DeploymentMode = DeploymentMode.DEVELOPMENT) -> Config:
    """
    Initialize global configuration.
    
    Args:
        mode: Deployment mode
        
    Returns:
        Initialized Config object
    """
    global _config
    _config = Config(MODE=mode)
    return _config
