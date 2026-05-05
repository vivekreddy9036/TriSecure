"""
TRIsecure package initialization.

Exports main system components.
"""

from .config import Config, DeploymentMode, get_config, setup_logging

# Legacy compatibility: some deployments used a main.py entrypoint exporting
# TRIsecureSystem. The current workspace uses app.py instead, so keep import
# optional to avoid breaking package import and test discovery.
try:
    from .main import TRIsecureSystem
except ModuleNotFoundError:
    TRIsecureSystem = None

__version__ = "1.0.0"
__author__ = "TRIsecure Development Team"

__all__ = [
    'TRIsecureSystem',
    'Config',
    'DeploymentMode',
    'get_config',
    'setup_logging',
]
