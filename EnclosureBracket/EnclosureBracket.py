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

import adsk.core
import traceback

from commands.generateBracket.entry import start as _cmd_start
from commands.generateBracket.entry import stop as _cmd_stop


def run(context):
    try:
        _cmd_start()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Add-in failed to start:\n' + traceback.format_exc(),
            'Enclosure Bracket')


def stop(context):
    try:
        _cmd_stop()
    except Exception:
        pass
