#!/usr/bin/env python3
import gi
import os
import json
import subprocess
import atexit
import re
import argparse
import threading
import http.server
import webbrowser
from urllib.parse import urlparse, parse_qs
from pathlib import Path

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')
from gi.repository import Gtk, WebKit2, GLib, Gdk

GUAC_LOGIN_URL = "https://desktop.rc.nectar.org.au/"
CACHE_DIR = os.path.expanduser("~/.cache/guac-webkit")
KEYBINDING_CACHE = os.path.join(CACHE_DIR, "gnome-keybindings.json")
REDIRECT_PORT = 34567
REDIRECT_PATH = f"http://localhost:{REDIRECT_PORT}/"

GNOME_KEYS = {
    "org.gnome.mutter": {
        "overlay-key": None,
    },
    "org.gnome.desktop.wm.keybindings": {
        "switch-windows": None,
        "switch-windows-backward": None,
        "switch-applications": None,
        "switch-applications-backward": None,
    }
}


class RedirectHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [None])[0]

        if token:
            full_url = f"https://desktop-qriscloud.rc.nectar.org.au/#/client/{token}"
            print(f"[redirect] Final Guac URL: {full_url}")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Launching Guacamole in app window...</h2></body></html>")
            self.server.parent_app.load_guacamole_url(full_url)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body>Waiting for Guacamole session token...</body></html>")

    def log_message(self, format, *args):
        pass  # suppress noisy logging


class GuacApp:
    def __init__(self, auth_mode):
        self.auth_mode = auth_mode
        os.makedirs(CACHE_DIR, exist_ok=True)
        if os.path.exists(KEYBINDING_CACHE):
            print("[gnome] Previous session ended unexpectedly — restoring keybindings...")
            self.restore_gnome_keys()

        data_manager = WebKit2.WebsiteDataManager(
            base_data_directory=CACHE_DIR,
            base_cache_directory=CACHE_DIR,
        )
        self.context = WebKit2.WebContext.new_with_website_data_manager(data_manager)

        self.window = Gtk.Window(title="Guacamole Desktop")
        self.window.connect("destroy", Gtk.main_quit)
        self.window.set_default_size(1280, 800)
        self.window.connect("key-press-event", self.on_key_press)

        self.webview = WebKit2.WebView.new_with_context(self.context)
        self.webview.connect("create", self.handle_create)
        self.webview.connect("decide-policy", self.on_decide_policy)
        self.webview.connect("load-changed", self.on_load_changed)
        self.window.add(self.webview)
        self.window.show_all()

        atexit.register(self.restore_gnome_keys)

        # app-only mode: always load Guacamole in embedded WebView
        print(f"[webkit] App-mode login: {GUAC_LOGIN_URL}")
        self.webview.load_uri(GUAC_LOGIN_URL)

    def start_redirect_server(self):
        self.server = http.server.HTTPServer(('localhost', REDIRECT_PORT), RedirectHandler)
        self.server.parent_app = self
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        print(f"[server] Listening on {REDIRECT_PATH}")

    def load_guacamole_url(self, url):
        GLib.idle_add(self.webview.load_uri, url)

    def get_gsetting(self, schema, key):
        result = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True)
        return result.stdout.strip()

    def set_gsetting(self, schema, key, value):
        subprocess.call(["gsettings", "set", schema, key, value])

    def backup_current_keys(self):
        backup = {}
        for schema, keys in GNOME_KEYS.items():
            for key in keys:
                current = self.get_gsetting(schema, key)
                backup.setdefault(schema, {})[key] = current
        with open(KEYBINDING_CACHE, 'w') as f:
            json.dump(backup, f)
        print("[gnome] Backed up GNOME keybindings")

    def disable_gnome_keys(self):
        print("[gnome] Disabling GNOME key grabs")
        self.backup_current_keys()
        self.set_gsetting("org.gnome.mutter", "overlay-key", "''")
        for schema, keys in GNOME_KEYS.items():
            for key in keys:
                self.set_gsetting(schema, key, "[]")

    def restore_gnome_keys(self):
        if not os.path.exists(KEYBINDING_CACHE):
            return
        print("[gnome] Restoring GNOME keybindings")
        try:
            with open(KEYBINDING_CACHE, 'r') as f:
                backup = json.load(f)
            for schema, keys in backup.items():
                for key, value in keys.items():
                    self.set_gsetting(schema, key, value)
            os.remove(KEYBINDING_CACHE)
        except Exception as e:
            print(f"[gnome] Failed to restore keybindings: {e}")

    def handle_create(self, webview, navigation_action):
        uri = navigation_action.get_request().get_uri()
        print(f"[webkit] New window request → {uri}")
        GLib.idle_add(self.webview.load_uri, uri)
        return self.webview

    def on_decide_policy(self, webview, decision, decision_type):
        uri = decision.get_request().get_uri()
        print(f"[webkit] decide-policy: {uri}")
        return False

    def on_load_changed(self, webview, load_event):
        uri = webview.get_uri()
        if uri:
            print(f"[webkit] load-changed: {uri}")

    def toggle_fullscreen(self):
        is_fullscreen = self.window.get_window().get_state() & Gdk.WindowState.FULLSCREEN
        if is_fullscreen:
            self.window.unfullscreen()
            self.restore_gnome_keys()
            print("[fullscreen] Exiting fullscreen")
        else:
            self.window.fullscreen()
            self.disable_gnome_keys()
            print("[fullscreen] Entering fullscreen")

    def paste_clipboard_into_guac(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if text:
            js_safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            js = f"document.execCommand('insertText', false, '{js_safe_text}');"
            self.webview.run_javascript(js, None, None, None)
            print("[paste] Injected clipboard text into Guac")
        else:
            print("[paste] Clipboard empty or not text")

    def on_key_press(self, widget, event):
        state = event.state
        is_super = state & Gdk.ModifierType.SUPER_MASK
        is_ctrl = state & Gdk.ModifierType.CONTROL_MASK

        if is_super and is_ctrl:
            if event.keyval == Gdk.KEY_F11:
                self.toggle_fullscreen()
                return True
            elif event.keyval == Gdk.KEY_V:
                self.paste_clipboard_into_guac()
                return True
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guacamole Desktop Launcher")
    parser.add_argument("--auth", choices=["app"], default="app",
                        help="Authentication mode (only 'app' is supported)")
    args = parser.parse_args()
    GuacApp(auth_mode=args.auth)
    Gtk.main()

