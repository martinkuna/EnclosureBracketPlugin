# -*- coding: utf-8 -*-
# Author: Martin Kuna
# Description: Parametric device mounting bracket generator for structured
#              media enclosures (Legrand On-Q and similar). Runs as a
#              Fusion 360 Add-In with a native command dialog. Designed for
#              FDM printing.
#
#   Installation:
#     Utilities > ADD-INS > Scripts and Add-Ins > Add-Ins tab > "+"
#     Point it at the EnclosureBracket folder, then click Run
#     (optionally "Run on Startup"). The command appears in
#     SOLID > CREATE > "Enclosure Bracket".

import sys
import os
import adsk.core
import traceback

# Ensure the add-in root is on sys.path so sub-package imports resolve.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from commands.generateBracket.entry import start as _cmd_start
    from commands.generateBracket.entry import stop as _cmd_stop
    _IMPORT_ERR = None
except Exception as _e:
    _cmd_start = _cmd_stop = None
    _IMPORT_ERR = traceback.format_exc()


def run(context):
    if _IMPORT_ERR:
        adsk.core.Application.get().userInterface.messageBox(
            'Add-in failed to import:\n' + _IMPORT_ERR,
            'Enclosure Bracket')
        return
    try:
        _cmd_start()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Add-in failed to start:\n' + traceback.format_exc(),
            'Enclosure Bracket')


def stop(context):
    try:
        if _cmd_stop:
            _cmd_stop()
    except Exception:
        pass
