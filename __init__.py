"""
TRIsecure package initialization.

Exports main system components.
"""

from .config import Config, DeploymentMode, get_config, setup_logging
from .main import TRIsecureSystem

__version__ = "1.0.0"
__author__ = "TRIsecure Development Team"

__all__ = [
    'TRIsecureSystem',
    'Config',
    'DeploymentMode',
    'get_config',
    'setup_logging',
]
