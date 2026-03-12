#!/usr/bin/env python
"""
CLI wrapper for send_campaign management command.

Usage:
    python send.py --campaign taggiq --dry-run
    python send.py --campaign taggiq --limit 5
    python send.py --campaign kritno --tier A
"""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'outreach.settings')

import django
django.setup()

from django.core.management import call_command

if __name__ == '__main__':
    args = sys.argv[1:]
    call_command('send_campaign', *args)
