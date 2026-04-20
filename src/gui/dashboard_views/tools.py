# src/gui/tabs/tools_tab.py

import os
import zipfile
import subprocess
import webbrowser
import threading
import gettext
from pathlib import Path

from gi.repository import Gtk, Adw, GLib

_ = gettext.gettext

class ToolsTab(Gtk.Box):
    def __init__(self, dashboard):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(100)
        self.set_margin_end(100)
        self.set_margin_top(40)
        
        self.dashboard = dashboard
        
        # Récupération de la config des utilitaires
        utilities_cfg = self.dashboard.game_config.get("essential-utilities", {})
        
        if not utilities_cfg or not isinstance(utilities_cfg, dict):
            self.append(Gtk.Label(label=_("No utilities defined."), css_classes=["dim-label"]))
        else:
            list_box = Gtk.ListBox(css_classes=["boxed-list"])
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)

            for util_id, util in utilities_cfg.items():
                row = Adw.ActionRow(title=util.get("name", util_id))
                
                # --- CREATOR BADGE (Prefix) ---
                creator = util.get("creator", "Unknown")
                link = util.get("creator-link", "#")
                
                creator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                creator_box.set_valign(Gtk.Align.CENTER)
                creator_box.set_margin_end(12)
                
                creator_btn = Gtk.Button(label=creator)
                creator_btn.add_css_class("flat")
                creator_btn.add_css_class("badge-action-row") 
                creator_btn.set_cursor_from_name("pointer")
                creator_btn.connect("clicked", lambda b, l=link: webbrowser.open(l))
                
                creator_box.append(creator_btn)
                row.add_prefix(creator_box)

                # --- VERSION BADGE (Suffix) ---
                util_version = util.get("version", "—")
                
                version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                version_badge.set_valign(Gtk.Align.CENTER)
                version_badge.set_margin_end(15)
                
                v_label = Gtk.Label(label=util_version)
                v_label.add_css_class("badge-action-row")
                
                version_badge.append(v_label)
                row.add_suffix(version_badge)

                # --- Path & Installation Logic ---
                source = util.get("source", "")
                filename = source.split("/")[-1] if "/" in source else f"{util_id}.zip"
                util_dir = Path(self.dashboard.downloads_path) / "utilities"
                local_zip_path = util_dir / filename
                target_dir = Path(self.dashboard.game_path) / util.get("utility_path", "")

                is_installed = False
                if local_zip_path.exists():
                    try:
                        with zipfile.ZipFile(local_zip_path, 'r') as z:
                            is_installed = all((target_dir / name).exists() for name in z.namelist() if not name.endswith('/'))
                    except: 
                        is_installed = False

                stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
                
                dl_btn = Gtk.Button(label=_("Download"), css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
                dl_btn.connect("clicked", self.on_utility_download_clicked, util, stack)
                
                inst_btn = Gtk.Button(label=_("Reinstall") if is_installed else "Install", valign=Gtk.Align.CENTER)
                if not is_installed: 
                    inst_btn.add_css_class("suggested-action")
                inst_btn.connect("clicked", self.on_utility_install_clicked, util)
                
                stack.add_named(dl_btn, "download")
                stack.add_named(inst_btn, "install")
                stack.set_visible_child_name("install" if local_zip_path.exists() else "download")
                
                row.add_suffix(stack)
                list_box.append(row)
            
            scrolled = Gtk.ScrolledWindow(vexpand=True)
            scrolled.set_child(list_box)
            self.append(scrolled)

        # --- Load Order Button ---
        load_order_rel = self.dashboard.game_config.get("load_order_path")
        if load_order_rel:
            btn_container = Gtk.CenterBox(margin_top=20, margin_bottom=20)
            load_order_btn = Gtk.Button(label=_("Edit Load Order"), css_classes=["pill"])
            load_order_btn.set_size_request(200, 40)
            load_order_btn.set_cursor_from_name("pointer")
            # Appel à load_text_file qui reste sur le dashboard principal
            load_order_btn.connect("clicked", self.dashboard.load_text_file, Path(self.dashboard.game_path) / load_order_rel)
            btn_container.set_center_widget(load_order_btn)
            self.append(btn_container)

    def on_utility_download_clicked(self, btn, util, stack):
        source_url = util.get("source")
        if not source_url: return

        util_dir = Path(self.dashboard.downloads_path) / "utilities"
        util_dir.mkdir(parents=True, exist_ok=True)
        
        filename = source_url.split("/")[-1]
        target_file = util_dir / filename

        def download_thread():
            try:
                import urllib.request
                urllib.request.urlretrieve(source_url, target_file)
                GLib.idle_add(lambda: stack.set_visible_child_name("install"))
            except Exception as e:
                GLib.idle_add(self.dashboard.show_message, "Download Failed", str(e))

        threading.Thread(target=download_thread, daemon=True).start()

    def on_utility_install_clicked(self, btn, util):
        msg = _("Warning: This process may be destructive to existing game files. Please ensure you have backed up your game directory before proceeding.")
        
        dialog = Adw.MessageDialog(
            transient_for=self.dashboard.app.win,
            heading=_("Confirm Installation"),
            body=msg
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("install", _("Install Anyway"))
        dialog.set_response_appearance("install", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(d, response_id):
            if response_id == "install":
                self.execute_utility_install(util)
            d.close()

        dialog.connect("response", on_response)
        dialog.present()

    def execute_utility_install(self, util):
        try:
            source_url = util.get("source")
            filename = source_url.split("/")[-1]
            zip_path = Path(self.dashboard.downloads_path) / "utilities" / filename
            
            game_root = Path(self.dashboard.game_path)
            install_subpath = util.get("utility_path", "")
            target_dir = game_root / install_subpath
            target_dir.mkdir(parents=True, exist_ok=True)

            whitelist = util.get("whitelist", [])
            blacklist = util.get("blacklist", [])

            with zipfile.ZipFile(zip_path, 'r') as z:
                if not whitelist and not blacklist:
                    z.extractall(target_dir)
                else:
                    for file_info in z.infolist():
                        file_name = file_info.filename
                        if whitelist and not any(allowed in file_name for allowed in whitelist):
                            continue
                        if blacklist and any(blocked in file_name for blocked in blacklist):
                            continue
                        z.extract(file_info, target_dir)

            cmd = util.get("enable_command")
            if cmd:
                subprocess.run(cmd, shell=True, cwd=game_root)

            self.dashboard.show_message(
                _("Success"),
                _("{} has been installed.").format(util.get('name'))
            )
        except Exception as e:
            self.dashboard.show_message(_("Installation Error"), str(e))