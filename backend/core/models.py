from enum import Enum

class Framework(str, Enum):
    """Supported modding frameworks."""
    FORGE = "forge"
    FABRIC = "fabric"
    NEOFORGE = "neoforge"