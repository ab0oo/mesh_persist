"""Config Functions.

This module contains the config file loading functions
"""

import sys
from configparser import ConfigParser


def load_config(filename: str, section: str) -> dict:
    """Reads configfile configuration for mesh_persist components."""
    parser = ConfigParser()
    parser.read(filename)

    # get section
    config = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            config[param[0]] = param[1]
    else:
        sys.exit(1)

    return config
