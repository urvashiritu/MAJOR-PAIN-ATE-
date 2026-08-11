#!/usr/bin/env python3
"""Shared UA regex patterns for the cleaning transform (src/00) and its
contract checks (src/03).

These literals must stay identical in both files: src/03 checks the flags
that src/00's TRANSFORM produces, so a pattern change must land in both.
Interpolate them into SQL strings as regexp_matches(x, '(?i){CONSTANT}').
"""
IOS_WEBKIT = r"CriOS|EdgiOS|FxiOS"
IOS_TOKEN = r"(^|[^A-Za-z0-9])(iPhone|iPad|iPod|iOS)($|[^A-Za-z0-9])"
ANDROID_TOKEN = r"(Android|Andorid)([^@]|$)"
DESKTOP_OS_MARKER = r"Mac OS X|Macintosh|Windows NT|X11;|CrOS"
