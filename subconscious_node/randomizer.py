"""
Handles random seed management for consistent but non-repetitive generation.
"""
import random
import time
from datetime import datetime

def get_time_based_seed():
    """Get a seed based on current time with millisecond precision"""
    return int(datetime.now().timestamp() * 1000)

def reset_seed():
    """Reset random seed using current time"""
    random.seed(get_time_based_seed())

def get_jittered_temperature(base_temp: float) -> float:
    """Add significant randomness to temperature for more varied generation while maintaining coherence"""
    jitter = random.random() * 0.4 - 0.2  # More aggressive jitter between -0.2 and 0.2
    # Use sigmoid-like curve to keep values in reasonable range
    # Higher base temps get more positive jitter, lower base temps get more negative
    jitter *= (1 - base_temp) if jitter < 0 else base_temp
    return max(0.1, min(1.0, base_temp + jitter))
