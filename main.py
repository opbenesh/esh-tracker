#!/usr/bin/env python3
"""
Spotify Release Tracker - CLI Entry Point
"""
import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from artist_tracker.tracker import main

if __name__ == '__main__':
    main()
