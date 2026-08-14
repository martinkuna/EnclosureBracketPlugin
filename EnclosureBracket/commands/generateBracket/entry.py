# -*- coding: utf-8 -*-
import adsk.core
import adsk.fusion
import traceback

from .build import build, Builder, MM

PRESETS = [
    {'key': 'ucg_fiber',   'label': 'UniFi Cloud Gateway Fiber',
     'dev_w': 220.0, 'dev_d': 105.0,  'dev_h':  45.0, 'dev_corner_r': 10.0,
     'hook_style': 'round',  'hook_leg':  0.0},
    {'key': 'mac_mini_m4', 'label': 'Mac mini (M4, 2024)',
     'dev_w': 127.0, 'dev_d': 127.0,  'dev_h':  50.0, 'dev_corner_r': 12.0,
     'hook_style': 'round',  'hook_leg':  0.0},
    {'key': 'mac_mini_m2', 'label': 'Mac mini (M1/M2, 2020-2023)',
     'dev_w': 197.0, 'dev_d': 197.0,  'dev_h':  36.0, 'dev_corner_r': 15.0,
     'hook_style': 'round',  'hook_leg':  0.0},
    {'key': 'rpi5_case',   'label': 'Raspberry Pi 5 - official case',
     'dev_w':  92.0, 'dev_d':  62.0,  'dev_h':  32.0, 'dev_corner_r':  4.0,
     'hook_style': 'square', 'hook_leg': 16.0},
    {'key': 'rpi_bare',    'label': 'Raspberry Pi bare board (4B/5)',
     'dev_w':  85.0, 'dev_d':  56.0,  'dev_h':  20.0, 'dev_corner_r':  3.0,
     'hook_style': 'square', 'hook_leg': 14.0},
    {'key': 'hdd_35',      'label': '3.5 inch hard drive',
     'dev_w': 147.0, 'dev_d': 101.6,  'dev_h':  26.1, 'dev_corner_r':  2.0,
     'hook_style': 'square', 'hook_leg': 22.0},
    {'key': 'hdd_25',      'label': '2.5 inch hard drive / SSD (9.5 mm)',
     'dev_w': 100.0, 'dev_d':  69.85, 'dev_h':   9.5, 'dev_corner_r':  2.0,
     'hook_style': 'square', 'hook_leg': 18.0},
    {'key': 'custom',      'label': 'Custom device',
     'dev_w': 150.0, 'dev_d': 100.0,  'dev_h':  30.0, 'dev_corner_r':  5.0,
     'hook_style': 'square', 'hook_leg': 18.0},
]

CMD_ID       = 'EnclosureBracketGen'
CMD_NAME     = 'Enclosure Bracket'
CMD_DESC     = ('Generate a parametric device mounting bracket for '
                'media enclosures (Legrand On-Q and similar).')
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID     = 'SolidCreatePanel'

_handlers = []   # GC protection for event handler objects


# =============================================================================
#  Command dialog helpers
# =============================================================================

def _mm_val(s):
    """ValueInput from a mm string, e.g. '5.00 mm'."""
    return adsk.core.ValueInput.createByString(s)


def _get_mm(inputs, input_id):
    """Read a ValueCommandInput's value and convert from cm to mm."""
    return inputs.itemById(input_id).value / MM


def _get_bool(inputs, input_id):
    return inputs.itemById(input_id).value


# =============================================================================
#  Command event handlers
# =============================================================================

class _CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            cmd = args.command
            cmd.isRepeatable = False
            cmd.setDialogInitialSize(420, 800)
            cmd.setDialogMinimumSize(380, 500)

            on_exec = _CommandExecuteHandler()
            cmd.execute.add(on_exec)
            _handlers.append(on_exec)

            on_changed = _CommandInputChangedHandler(cmd.commandInputs)
            cmd.inputChanged.add(on_changed)
            _handlers.append(on_changed)

            on_destroy = _CommandDestroyHandler()
            cmd.destroy.add(on_destroy)
            _handlers.append(on_destroy)

            inputs = cmd.commandInputs

            # -- Note ---------------------------------------------------------
            inputs.addTextBoxCommandInput(
                'note', '',
                '<b>Measure your device with calipers!</b>\nInfo for inputs can be found <a href=\"https://github.com/martinkuna/EnclosureBracketPlugin\">on our GitHub</a>.', 2, True)

            # -- Preset dropdown ----------------------------------------------
            dd = inputs.addDropDownCommandInput(
                'preset', 'Preset',
                adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, p in enumerate(PRESETS):
                dd.listItems.add(p['label'], i == 0)

            p0 = PRESETS[0]

            # -- Device group -------------------------------------------------
            grp_dev = inputs.addGroupCommandInput('grp_device', 'Device dimensions')
            gi = grp_dev.children

            gi.addValueInput('dev_w', 'Width (X)', 'mm',
                             _mm_val('%.2f mm' % p0['dev_w']))
            gi.addValueInput('dev_d', 'Depth (Y)', 'mm',
                             _mm_val('%.2f mm' % p0['dev_d']))
            gi.addValueInput('dev_h', 'Height (Z)', 'mm',
                             _mm_val('%.2f mm' % p0['dev_h']))
            gi.addValueInput('dev_corner_r', 'Corner radius', 'mm',
                             _mm_val('%.2f mm' % p0['dev_corner_r']))

            dd_style = gi.addDropDownCommandInput(
                'hook_style', 'Hook style',
                adsk.core.DropDownStyles.TextListDropDownStyle)
            dd_style.listItems.add('Round', p0['hook_style'] == 'round')
            dd_style.listItems.add('Square', p0['hook_style'] == 'square')

            inp_leg = gi.addValueInput('hook_leg', 'Hook leg length', 'mm',
                                       _mm_val('%.2f mm' % p0['hook_leg']))
            inp_leg.isVisible = (p0['hook_style'] == 'square')

            # -- Plate & hooks group ------------------------------------------
            grp_plt = inputs.addGroupCommandInput('grp_plate', 'Plate & hooks')
            pi = grp_plt.children

            pi.addValueInput('plate_t',     'Plate thickness',        'mm', _mm_val('5.00 mm'))
            pi.addValueInput('fit_clear',   'Fit clearance (per side)','mm', _mm_val('0.40 mm'))
            pi.addValueInput('hook_t',      'Hook wall thickness',     'mm', _mm_val('2.80 mm'))
            pi.addValueInput('hook_lip',    'Retaining lip depth',     'mm', _mm_val('1.20 mm'))
            pi.addValueInput('hook_lip_h',  'Lip height',              'mm', _mm_val('1.60 mm'))
            pi.addValueInput('hook_fillet', 'Hook base fillet (0=off)','mm', _mm_val('3.00 mm'))
            pi.addValueInput('base_chamfer','Base chamfer (0=off)',    'mm', _mm_val('0.50 mm'))
            inp_support = pi.addValueInput('hook_support_w',
                                           'Corner support (0=off)',   'mm', _mm_val('4.00 mm'))
            inp_support.isVisible = (p0['hook_style'] == 'round')

            # -- Features group -----------------------------------------------
            grp_feat = inputs.addGroupCommandInput('grp_features', 'Features')
            fi = grp_feat.children

            fi.addBoolValueInput('center_cut',   'Center opening',         True, '', True)
            fi.addBoolValueInput('corner_slots', 'Corner plunger slots',   True, '', True)
            fi.addBoolValueInput('side_slots',   'Side plunger slots',     True, '', True)
            fi.addBoolValueInput('vents',        'Ventilation holes',      True, '', False)
            inp_vent_d = fi.addValueInput('vent_d', 'Vent diameter', 'mm',
                                          _mm_val('6.00 mm'))
            inp_vent_d.isVisible = False

        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Dialog creation failed:\n' + traceback.format_exc(),
                'Enclosure Bracket')


class _CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self, root_inputs):
        super().__init__()
        self._root_inputs = root_inputs

    def notify(self, args):
        try:
            changed = args.input
            inputs = self._root_inputs

            if changed.id == 'preset':
                p = PRESETS[changed.selectedItem.index]
                inputs.itemById('dev_w').value        = p['dev_w']        * MM
                inputs.itemById('dev_d').value        = p['dev_d']        * MM
                inputs.itemById('dev_h').value        = p['dev_h']        * MM
                inputs.itemById('dev_corner_r').value = p['dev_corner_r'] * MM
                dd_style = inputs.itemById('hook_style')
                if p['hook_style'] == 'round':
                    dd_style.listItems.item(0).isSelected = True
                else:
                    dd_style.listItems.item(1).isSelected = True
                inputs.itemById('hook_leg').value         = p['hook_leg']     * MM
                inputs.itemById('hook_leg').isVisible     = (p['hook_style'] == 'square')
                inputs.itemById('hook_support_w').isVisible = (p['hook_style'] == 'round')

            elif changed.id == 'hook_style':
                is_round = (changed.selectedItem.name == 'Round')
                inputs.itemById('hook_leg').isVisible       = not is_round
                inputs.itemById('hook_support_w').isVisible = is_round

            elif changed.id == 'vents':
                inputs.itemById('vent_d').isVisible = changed.value

        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Input changed handler failed:\n' + traceback.format_exc(),
                'Enclosure Bracket')


class _CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        b = None
        ui = None
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                ui.messageBox('Open a Fusion 360 design first, then run this '
                              'add-in.', 'Enclosure Bracket')
                return

            inputs = args.command.commandInputs

            hook_style_name = inputs.itemById('hook_style').selectedItem.name
            hook_style = 'round' if hook_style_name == 'Round' else 'square'

            dev = {
                'label':        inputs.itemById('preset').selectedItem.name,
                'dev_w':        _get_mm(inputs, 'dev_w'),
                'dev_d':        _get_mm(inputs, 'dev_d'),
                'dev_h':        _get_mm(inputs, 'dev_h'),
                'dev_corner_r': _get_mm(inputs, 'dev_corner_r'),
                'hook_style':   hook_style,
            }
            if hook_style == 'square':
                dev['hook_leg'] = _get_mm(inputs, 'hook_leg')

            vents_on = _get_bool(inputs, 'vents')
            cfg = {
                'fit_clear':       _get_mm(inputs, 'fit_clear'),
                'hook_h_adj':      0.20,
                'plate_t':         _get_mm(inputs, 'plate_t'),
                'plate_corner_r':  None,
                'hook_t':          _get_mm(inputs, 'hook_t'),
                'hook_lip':        _get_mm(inputs, 'hook_lip'),
                'hook_lip_h':      _get_mm(inputs, 'hook_lip_h'),
                'hook_inner_r':    1.50,
                'hook_fillet':     _get_mm(inputs, 'hook_fillet'),
                'base_chamfer':    _get_mm(inputs, 'base_chamfer'),
                'hook_support_w':  _get_mm(inputs, 'hook_support_w'),
                'waist_d_x':       None,
                'waist_d_y':       None,
                'waist_margin':    3.00,
                'center_cut':      _get_bool(inputs, 'center_cut'),
                'center_l':        None,
                'center_w':        None,
                'slot_w':          6.60,
                'inset_w':         9.40,
                'inset_t':         3.00,
                'corner_slots':    _get_bool(inputs, 'corner_slots'),
                'corner_slot_len': None,
                'side_slots':      _get_bool(inputs, 'side_slots'),
                'side_slot_axis':  'auto',
                'side_slot_len':   None,
                'edge_margin':     2.50,
                'straps':          [],
                'extra_slots':     [],
                'vents':           vents_on,
                'vent_d':          _get_mm(inputs, 'vent_d') if vents_on else 6.0,
                'vent_pitch':      10.00,
                'vent_pattern':    'hex',
                'vent_margin':     2.50,
            }

            design.designType = adsk.fusion.DesignTypes.ParametricDesignType
            try:
                design.fusionUnitsManager.distanceDisplayUnits = \
                    adsk.fusion.DistanceUnits.MillimeterDistanceUnits
            except Exception:
                pass

            preset_idx  = inputs.itemById('preset').selectedItem.index
            preset_key  = PRESETS[preset_idx]['key']
            root = design.rootComponent
            try:
                occ  = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
                comp = occ.component
                comp.name = 'Bracket_' + preset_key
            except RuntimeError:
                # Part Design mode only allows one component — build in root.
                comp = root

            b    = Builder(app, ui, design, comp)
            info = build(b, dev, cfg)

            msg = [
                'Bracket generated: ' + dev['label'],
                '',
                'Hook style      : ' + info['style'],
                'Plate           : %.1f x %.1f x %.1f mm'
                % (info['plate_l'], info['plate_w'], b.pval('plate_t')),
                'Corner radius   : %.2f mm' % info['corner_r'],
                'Hook height     : %.2f mm (device is %.2f mm)'
                % (info['hook_h'], dev['dev_h']),
            ]
            if info['style'] == 'square':
                msg.append('Hook leg        : %.1f mm' % info['hook_leg'])
            msg += [
                'Waist depth     : %.1f mm (X) / %.1f mm (Y)'
                % (info['waist_d_x'], info['waist_d_y']),
                'Central opening : %.1f x %.1f mm'
                % (info['center_l'], info['center_w']),
                'Slots           : %d' % info['n_slots'],
            ]
            if b.notes:
                msg += [''] + b.notes
            if b.warnings:
                msg += ['', 'Warnings:'] + ['  - ' + w for w in b.warnings]
            msg += ['',
                    'Edit values under Modify > Change Parameters.',
                    'CHECK FIT against the real device before printing.']
            ui.messageBox('\n'.join(msg), 'Enclosure Bracket Generator')

        except Exception:
            stage = b.stage if b else 'startup'
            if ui:
                ui.messageBox('Build failed during: %s\n\n%s'
                              % (stage, traceback.format_exc()),
                              'Enclosure Bracket Generator – Error')


class _CommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        pass


def start():
    global _handlers
    _handlers = []
    app = adsk.core.Application.get()
    ui  = app.userInterface

    old = ui.commandDefinitions.itemById(CMD_ID)
    if old:
        old.deleteMe()

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_DESC, '')

    on_created = _CommandCreatedHandler()
    cmd_def.commandCreated.add(on_created)
    _handlers.append(on_created)

    ws = ui.workspaces.itemById(WORKSPACE_ID)
    if not ws:
        all_ws = [ui.workspaces.item(i).id
                  for i in range(ui.workspaces.count)]
        ui.messageBox(
            'Workspace "%s" not found.\n\nAvailable workspaces:\n%s'
            % (WORKSPACE_ID, '\n'.join(all_ws)),
            'Enclosure Bracket – debug')
        return

    panel = ws.toolbarPanels.itemById(PANEL_ID)
    if not panel:
        all_panels = [ws.toolbarPanels.item(i).id
                      for i in range(ws.toolbarPanels.count)]
        ui.messageBox(
            'Panel "%s" not found in workspace "%s".\n\n'
            'Available panels:\n%s'
            % (PANEL_ID, WORKSPACE_ID, '\n'.join(all_panels)),
            'Enclosure Bracket – debug')
        return

    ctrl = panel.controls.addCommand(cmd_def)
    ctrl.isPromoted = True


def stop():
    app = adsk.core.Application.get()
    ui  = app.userInterface

    ws = ui.workspaces.itemById(WORKSPACE_ID)
    if ws:
        panel = ws.toolbarPanels.itemById(PANEL_ID)
        if panel:
            ctrl = panel.controls.itemById(CMD_ID)
            if ctrl:
                ctrl.deleteMe()

    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()

    _handlers.clear()
