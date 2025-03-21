"""Config Functions.

This module contains the config file loading functions
"""

from configparser import ConfigParser
import sys

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
        err = f"Section {section} not found in the {filename} file"
        print(err)
        sys.exit(1)

    return config
