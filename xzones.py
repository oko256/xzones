#!/usr/bin/env python3

from Xlib import X, XK, Xutil
from Xlib.ext import record
from Xlib.ext import randr
from Xlib.display import Display
from Xlib.protocol import rq
import pprint
from pathlib import Path
import toml
import argparse
import uuid

CONFIG_FILE = str(Path.home() / ".xzones")
VERBOSE = False

def find_window(display: Display, window_id=None):
    if not window_id:
        window_id = display.screen().root.get_full_property(display.intern_atom('_NET_ACTIVE_WINDOW'), X.AnyPropertyType).value[0]
    try:
        return display.create_resource_object('window', window_id)
    except:
        return None

def find_preset_name_with_current_screens(display: Display, config):
    screen_data = display.xinerama_query_screens()._data
    for preset_name, preset in config.items():
        if 'screens' not in preset:
            continue
        if 'zones' not in preset:
            continue
        if 'count' not in preset['screens']:
            continue
        if preset['screens']['count'] != screen_data['number']:
            continue
        idx = 0
        matching_preset = True
        for sc in screen_data['screens']:
            if (preset['screens']['x'][idx] != sc['x']) or (preset['screens']['y'][idx] != sc['y']) or (preset['screens']['width'][idx] != sc['width']) or (preset['screens']['height'][idx] != sc['height']):
                matching_preset = False
                break
            idx += 1
        if matching_preset:
            return preset_name
    return None

def find_zone_rects(display: Display, config):
    preset_name = find_preset_name_with_current_screens(display, config)
    if preset_name:
        preset = config[preset_name]
        zone_rects = []
        for zone_name, z in preset['zones'].items():
            if ('x0' in z) and ('y0' in z) and ('x1' in z) and ('y1' in z):
                zone_rects.append(z)
        return zone_rects
    return []


class Daemon:
    def __init__(self, config):
        self.snap_activated = False
        self.config = config

        self.display = Display()
        self.root = self.display.screen().root

        # Record mouse button press/release and motion events
        self.context = self.display.record_create_context(
                0,
                [record.AllClients],
                [
                    {
                        'core_requests': (0, 0),
                        'core_replies': (0, 0),
                        'ext_requests': (0, 0, 0, 0),
                        'ext_replies': (0, 0, 0, 0),
                        'delivered_events': (0, 0),
                        'device_events': (X.ButtonPress, X.ButtonRelease),
                        'errors': (0, 0),
                        'client_started': False,
                        'client_died': False,
                        }
                    ],
                )
        self.display.record_enable_context(self.context, self.event_handler)
        self.display.record_free_context(self.context)

    def event_handler(self, reply):
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(
                    data, self.display.display, None, None
                    )

            if event.type == X.ButtonPress:
                if (event.detail == X.Button1) and (event.state & X.Button3MotionMask):
                    self.snap_activated = True
                elif (event.detail == X.Button3) and (event.state & X.Button1MotionMask):
                    self.snap_activated = True
            elif event.type == X.ButtonRelease:
                if self.snap_activated:
                    self.snap_active_window(event.root_x, event.root_y)
                self.snap_activated = False

    def snap_active_window(self, x, y):
        try:
            display = Display()
            window = find_window(display)
            if window is None:
                return
            window_geometry = window.get_geometry()
            parent_geometry = window.query_tree().parent.get_geometry()
            width_diff = parent_geometry.width - window_geometry.width
            height_diff = parent_geometry.height - window_geometry.height

            zone_rects = find_zone_rects(display, self.config)

            zone_x = None
            zone_y = None
            zone_w = None
            zone_h = None
            zone_found = False
            for z in zone_rects:
                if (x > z['x0']) and (x < z['x1']) and (y > z['y0']) and (y < z['y1']):
                    # Inside this zone
                    zone_x = z['x0']
                    zone_y = z['y0']
                    zone_w = z['x1'] - zone_x
                    zone_h = z['y1'] - zone_y
                    zone_found = True
                    break
            if zone_found:
                window.configure(
                        x=zone_x,
                        y=zone_y,
                        width=zone_w - width_diff,
                        height=zone_h - height_diff,
                        stack_mode=X.Above,
                        )
                display.sync()
        except:
            pass

    def run(self):
        while True:
            self.root.display.next_event()

class Configurator:
    class ZoneWindow:
        def __init__(self, display: Display, color, x, y, width, height):
            self.display = display
            self.screen = self.display.screen()

            self.window = self.screen.root.create_window(
                    x, y, width, height, 2,
                    self.screen.root_depth,
                    X.InputOutput,
                    X.CopyFromParent,
                    background_pixel = color,
                    event_mask = (X.ExposureMask | X.KeyPressMask | X.KeyReleaseMask),
                    colormap = X.CopyFromParent,
                    )

            self.WM_DELETE_WINDOW = self.display.intern_atom('WM_DELETE_WINDOW')
            self.WM_PROTOCOLS = self.display.intern_atom('WM_PROTOCOLS')

            self.window.set_wm_name('xzones')
            self.window.set_wm_icon_name('xzones')
            self.window.set_wm_class('xzones', 'xzones')

            self.window.set_wm_protocols([self.WM_DELETE_WINDOW])
            self.window.set_wm_hints(flags = Xutil.StateHint, initial_state = Xutil.NormalState)

            self.window.set_wm_normal_hints(flags = (Xutil.PPosition | Xutil.PSize | Xutil.PMinSize), min_width = 20, min_height = 20)

            self.window.map()

    def __init__(self, config):
        self.config = config
        self.display = Display()
        self.screen = self.display.screen()

        self.WM_DELETE_WINDOW = self.display.intern_atom('WM_DELETE_WINDOW')
        self.WM_PROTOCOLS = self.display.intern_atom('WM_PROTOCOLS')

        self.palette = [
                0x1F77B4FF,
                0xAEC7E8FF,
                0xFF7F0EFF,
                0xFFBB78FF,
                0x2CA02CFF,
                0x98DF8AFF,
                0xD62728FF,
                0xFF9896FF,
                0x9467BDFF,
                0xC5B0D5FF,
                0x8C564BFF,
                0xC49C94FF,
                0xE377C2FF,
                0xF7B6D2FF,
                0x7F7F7FFF,
                0xC7C7C7FF,
                0xBCBD22FF,
                0xDBDB8DFF,
                0x17BECFFF,
                0x9EDAE5FF,
                ]

        self.zone_windows = []
        zone_rects = find_zone_rects(self.display, self.config)
        if len(zone_rects) == 0:
            self.zone_windows.append(self.ZoneWindow(self.display, self.palette[len(self.zone_windows)], 0, 0, 300, 300))
        else:
            for z in zone_rects:
                w = z['x1'] - z['x0']
                h = z['y1'] - z['y0']
                self.zone_windows.append(self.ZoneWindow(self.display, self.palette[len(self.zone_windows)], z['x0'], z['y0'], w, h))

    def run(self):
        while True:
            e = self.display.next_event()

            if e.type == X.DestroyNotify:
                return

            if e.type == X.KeyPress:
                keysym = self.display.keycode_to_keysym(e.detail, 0)
                if keysym in (XK.XK_n, XK.XK_N):
                    self.zone_windows.append(self.ZoneWindow(self.display, self.palette[len(self.zone_windows)], 0, 0, 300, 300))
                elif keysym in (XK.XK_d, XK.XK_D):
                    window = find_window(self.display)
                    zone_window_to_delete = None
                    if window:
                        for w in self.zone_windows:
                            if w.window == window:
                                zone_window_to_delete = w
                                break
                        window.destroy()
                        if zone_window_to_delete:
                            self.zone_windows.remove(zone_window_to_delete)
                            if len(self.zone_windows) == 0:
                                return
                elif keysym in (XK.XK_q, XK.XK_Q):
                    return
                elif keysym in (XK.XK_s, XK.XK_S):
                    self.update_config()

            if VERBOSE:
                print(".", end="", flush=True)

    def update_config(self):
        preset_name = find_preset_name_with_current_screens(self.display, self.config)
        preset = {}
        if preset_name:
            preset = self.config[preset_name]
        else:
            screen_data = self.display.xinerama_query_screens()._data
            preset['screens'] = { 'count': screen_data['number'], 'x': [], 'y': [], 'width': [], 'height': [] }
            for sc in screen_data['screens']:
                preset['screens']['x'].append(sc['x'])
                preset['screens']['y'].append(sc['y'])
                preset['screens']['width'].append(sc['width'])
                preset['screens']['height'].append(sc['height'])

        preset['zones'] = {}
        for w in self.zone_windows:
            id = str(uuid.uuid4())
            window_geometry = w.window.get_geometry()
            parent_geometry = w.window.query_tree().parent.get_geometry()
            preset['zones'][id] = {
                    'x0': parent_geometry.x,
                    'y0': parent_geometry.y,
                    'x1': parent_geometry.x + parent_geometry.width,
                    'y1': parent_geometry.y + parent_geometry.height,
                    }

        if not preset_name:
            preset_name = str(uuid.uuid4())
            self.config[preset_name] = preset

        with open(CONFIG_FILE, 'w') as f:
            toml.dump(self.config, f)

if __name__ == '__main__':
    try:
        config = toml.load(CONFIG_FILE)
    except:
        config = {}

    parser = argparse.ArgumentParser(prog='xzones', description="Running without arguments starts the configuration mode.")
    parser.add_argument('-d', '--daemon', help="Run as the daemon that allows the use of zones", action='store_true')
    parser.add_argument('-v', '--verbose', help="Enable verbose debug output", action='store_true')
    args = parser.parse_args()
    if args.verbose:
        VERBOSE = True
        print("Verbose debug output enabled.")
    if args.daemon:
        d = Daemon(config)
        d.run()
    else:
        c = Configurator(config)
        c.run()
