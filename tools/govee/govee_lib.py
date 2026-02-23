#!/usr/bin/env python3
"""
Govee API Library
Handles communication with Govee API for device control
"""

import os
import requests
import json
from typing import List, Dict, Optional, Tuple

API_BASE = "https://developer-api.govee.com/v1"

def get_api_key() -> str:
    """Load API key from environment or .env file"""
    # Check environment first
    api_key = os.environ.get("GOVEE_API_KEY")
    if api_key:
        return api_key
    
    raise ValueError("GOVEE_API_KEY not found in environment")

def make_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
    """Make authenticated request to Govee API"""
    api_key = get_api_key()
    headers = {
        "Govee-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    url = f"{API_BASE}{endpoint}"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "PUT":
        response = requests.put(url, headers=headers, json=data)
    else:
        raise ValueError(f"Unsupported method: {method}")
    
    response.raise_for_status()
    return response.json()

def list_devices() -> List[Dict]:
    """Get all Govee devices"""
    result = make_request("GET", "/devices")
    return result.get("data", {}).get("devices", [])

def control_device(device: str, model: str, cmd: Dict) -> Dict:
    """Send control command to device"""
    data = {
        "device": device,
        "model": model,
        "cmd": cmd
    }
    return make_request("PUT", "/devices/control", data)

def set_power(device: str, model: str, on: bool) -> Dict:
    """Turn device on or off"""
    cmd = {"name": "turn", "value": "on" if on else "off"}
    return control_device(device, model, cmd)

def set_brightness(device: str, model: str, brightness: int) -> Dict:
    """Set brightness (0-100)"""
    if not 0 <= brightness <= 100:
        raise ValueError("Brightness must be 0-100")
    cmd = {"name": "brightness", "value": brightness}
    return control_device(device, model, cmd)

def set_color(device: str, model: str, r: int, g: int, b: int) -> Dict:
    """Set RGB color (0-255 each)"""
    if not all(0 <= c <= 255 for c in [r, g, b]):
        raise ValueError("RGB values must be 0-255")
    cmd = {"name": "color", "value": {"r": r, "g": g, "b": b}}
    return control_device(device, model, cmd)

def set_color_temp(device: str, model: str, temp: int) -> Dict:
    """Set color temperature in Kelvin (2000-9000)"""
    if not 2000 <= temp <= 9000:
        raise ValueError("Color temp must be 2000-9000K")
    cmd = {"name": "colorTem", "value": temp}
    return control_device(device, model, cmd)

def parse_color_name(color: str) -> Tuple[int, int, int]:
    """Convert color name to RGB"""
    colors = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255),
        "white": (255, 255, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "purple": (128, 0, 128),
        "orange": (255, 165, 0),
        "pink": (255, 192, 203),
        "warm": (255, 200, 120),  # Warm white
        "cool": (200, 220, 255),  # Cool white
    }
    color_lower = color.lower()
    if color_lower not in colors:
        raise ValueError(f"Unknown color: {color}. Available: {', '.join(colors.keys())}")
    return colors[color_lower]

def find_device(name_or_mac: str, devices: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Find device by name (partial match) or MAC address"""
    if devices is None:
        devices = list_devices()
    
    name_or_mac_lower = name_or_mac.lower()
    
    # Try exact MAC match first
    for device in devices:
        if device["device"].lower() == name_or_mac_lower:
            return device
    
    # Try partial name match
    for device in devices:
        if name_or_mac_lower in device["deviceName"].lower():
            return device
    
    return None