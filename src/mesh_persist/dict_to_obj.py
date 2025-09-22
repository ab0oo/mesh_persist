"""Helper function for dictionary to Object.

This helper class converts a python dictionary to an Object
"""


class DictToObject:
    """Helper class to convert a python dictionary to a python object."""

    def __init__(self, dictionary: dict) -> None:
        """Initialization for class."""
        for key, value in dictionary.items():
            if isinstance(value, dict):
                setattr(self, key, DictToObject(value))  # Recursively handle nested dictionaries
            elif isinstance(value, list):
                # Handle lists containing dictionaries or other types
                setattr(self, key, [DictToObject(item) if isinstance(item, dict) else item for item in value])
            else:
                setattr(self, key, value)
