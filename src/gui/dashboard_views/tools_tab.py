# src/gui/tabs/tools_tab.py

# Ce fichier fait partie de Yamm (Yet Another Mod Manager).
# Yamm est un fork de Nomm, développé initialement par Allexio.
#
# Copyright (C) 2026 Emetros
# Copyright (C) 2024 Allexio
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier
# selon les termes de la Licence Publique Générale GNU telle que publiée par la
# Free Software Foundation, soit la version 3 de la Licence, soit (à votre
# discrétion) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE
# GARANTIE ; sans même la garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la Licence Publique Générale GNU
# pour plus de détails.
#
# Vous devriez avoir reçu une copie de la Licence Publique Générale GNU
# avec ce programme. Sinon, voir <https://www.gnu.org/licenses/>.

import os
import webbrowser
import threading
import gettext

from core.mod_manager import is_utility_installed, deploy_essential_utility

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

                is_installed = is_utility_installed(local_zip_path, target_dir)

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
        if not source_url: 
            return

        # On prépare le chemin du dossier
        util_dir = os.path.join(self.dashboard.downloads_path, "utilities")

        # 1. Ce qu'il faut faire en cas de succès
        def on_success():
            stack.set_visible_child_name("install")

        # 2. Ce qu'il faut faire en cas d'erreur
        def on_error(error_msg):
            self.dashboard.show_message(_("Download Failed"), error_msg)

        # 3. On délègue tout le travail fastidieux au Core !
        download_file_async(source_url, util_dir, on_success, on_error)

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
        """Appelle la logique métier pour installer le framework, et gère les messages UI."""
        try:
            # On appelle le core !
            deploy_essential_utility(util, self.dashboard.downloads_path, self.dashboard.game_path)
            
            self.dashboard.show_message(
                _("Success"),
                _("{} has been installed.").format(util.get('name'))
            )
        except Exception as e:
            self.dashboard.show_message(_("Installation Error"), str(e))