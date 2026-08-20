#!/usr/bin/env python3
"""Live User-Agent parsing.

Derives device_type / os_family / browser_family from a real browser
User-Agent string, mirroring the vocabulary the training pipeline uses
(src/00_clean_dataset.py + src/_ua_patterns.py): mobile/desktop/tablet,
iOS/Android/Windows/ChromeOS/macOS/Linux, Chrome/Chrome Mobile/Firefox/
Safari/Edge/Samsung Internet. Pure stdlib so the live app has no new deps.
"""
import re

IOS_WEBKIT = re.compile(r"CriOS|EdgiOS|FxiOS", re.I)
IOS_TOKEN = re.compile(r"(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])", re.I)
ANDROID_TOKEN = re.compile(r"(Android|Andorid)([^@]|$)", re.I)
DESKTOP_OS_MARKER = re.compile(r"Mac OS X|Macintosh|Windows NT|X11;|CrOS", re.I)
MOBILE_TOKEN = re.compile(r"(^|[^A-Za-z0-9])Mobile($|[^A-Za-z0-9])", re.I)
TABLET_MARKERS = re.compile(
    r"iPad|Tablet|SM-T|Tab S|Tab A|Galaxy Tab|Nexus (7|9|10)|Xoom|KFAPWI|Lenovo TAB", re.I)


def os_family(ua: str) -> str:
    if re.search(r"Windows Phone", ua, re.I):
        return "Windows Phone"
    if (IOS_WEBKIT.search(ua) or IOS_TOKEN.search(ua)) \
            and not ANDROID_TOKEN.search(ua) and not re.search(r"Windows Phone", ua, re.I):
        return "iOS"
    if ANDROID_TOKEN.search(ua):
        return "Android"
    if re.search(r"Windows", ua, re.I):
        return "Windows"
    if re.search(r"X11; CrOS", ua, re.I):
        return "ChromeOS"
    if re.search(r"Mac OS X|Macintosh|Mac_PowerPC", ua, re.I):
        return "macOS"
    if re.search(r"Linux|X11", ua, re.I):
        return "Linux"
    return "unknown"


def device_type(ua: str) -> str:
    if TABLET_MARKERS.search(ua):
        return "tablet"
    if re.search(r"iPhone|iPod|Windows Phone", ua, re.I) or ANDROID_TOKEN.search(ua):
        return "mobile"
    if MOBILE_TOKEN.search(ua) and not DESKTOP_OS_MARKER.search(ua):
        return "mobile"
    return "desktop"


def browser_family(ua: str, device: str) -> str:
    if re.search(r"Edg|Edge", ua, re.I):
        return "Edge"
    if re.search(r"Firefox|FxiOS", ua, re.I):
        return "Firefox"
    if re.search(r"SamsungBrowser", ua, re.I):
        return "Samsung Internet"
    if re.search(r"CriOS|HeadlessChrome|Chrome", ua, re.I):
        return "Chrome Mobile" if device == "mobile" else "Chrome"
    if re.search(r"Safari", ua, re.I):
        return "Safari"
    return "Chrome"


def parse_user_agent(ua: str) -> dict:
    ua = ua or ""
    device = device_type(ua)
    return {
        "device_type": device,
        "os_family": os_family(ua),
        "browser_family": browser_family(ua, device),
    }