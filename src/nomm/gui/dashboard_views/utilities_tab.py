import gettext
import os
import threading
import webbrowser
from pathlib import Path
from urllib.parse import unquote
from gi.repository import Adw, Gtk

from nomm.core.mod_manager import deploy_essential_utility

_ = gettext.gettext


class UtilitiesTab(Gtk.Box):
    def __init__(self, dashboard, downloader):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(100)
        self.set_margin_end(100)
        self.set_margin_top(40)

        self.dashboard = dashboard
        self.downloader = downloader
        self.download_maps = {}

        utility_groups = self.dashboard.game_info.get("utilities", [])
        list_box = Gtk.ListBox(css_classes=["dashboard-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.set_overflow(Gtk.Overflow.HIDDEN)

        for utility in utility_groups:
            row = Adw.ActionRow(title=utility["name"])

            REQUIRED_FIELDS = ["name", "creator", "creator_link", "source_type", "source_url",
                               "executable_type", "deploy_to_game_files"]
            missing_fields = set(REQUIRED_FIELDS) - utility.keys()
            if missing_fields:
                print(f"[!] Missing required utility fields: {missing_fields}")
                if "name" in utility:
                    print(f"[!] Skipping utility: {utility["name"]}")
                else:
                    print("[!] Skipping utility")

            creator = utility["creator"]
            creator_link = utility["creator_link"]

            creator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            creator_box.set_valign(Gtk.Align.CENTER)
            creator_box.set_margin_end(12)

            creator_btn = Gtk.Button(label=creator)
            creator_btn.add_css_class("flat")
            creator_btn.add_css_class("badge-action-row")
            creator_btn.set_cursor_from_name("pointer")
            creator_btn.connect("clicked", lambda b, link=creator_link: webbrowser.open(link))

            creator_box.append(creator_btn)
            row.add_prefix(creator_box)

            # Version badge
            version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            version_badge.set_valign(Gtk.Align.CENTER)
            version_badge.set_margin_end(15)

            v_label = Gtk.Label(label=str(utility["version"]))
            v_label.add_css_class("badge-action-row")

            version_badge.append(v_label)
            row.add_suffix(version_badge)

            util_dir = Path(self.dashboard.downloads_path) / "utilities"
            staging_dir = Path(self.dashboard.staging_path) / "utilities" / utility["name"]

            stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

            # Download & install buttons
            dl_btn = Gtk.Button(label=_("Download"), css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
            inst_btn = Gtk.Button(valign=Gtk.Align.CENTER)

            if utility["source_type"] in ["direct", "github"]:
                decoded_url = unquote(utility["source_url"])
                if "/" in decoded_url:
                    file_name = decoded_url.split("/")[-1]
                else:
                    file_name = decoded_url

                current_ratio = None
                if file_name in self.download_maps:
                    current_ratio = self.download_maps[file_name].get_fraction()

                local_zip_path = util_dir / file_name

                dl_pbar = Gtk.ProgressBar()
                dl_pbar.set_can_target(False)
                dl_pbar.add_css_class('dl-tabs-pbar')
                dl_pbar.set_vexpand(True)
                dl_pbar.set_halign(Gtk.Align.FILL)
                dl_pbar.set_valign(Gtk.Align.FILL)
                dl_pbar.set_size_request(-1, -1)
                if current_ratio:
                    dl_pbar.set_fraction(current_ratio)
                self.download_maps[file_name] = dl_pbar
                dl_btn.connect("clicked", self.on_utility_download_clicked, utility, stack, dl_pbar, file_name)

                # Overlay to display download progress on top of download button
                overlay = Gtk.Overlay()
                overlay.set_halign(Gtk.Align.CENTER)
                overlay.set_valign(Gtk.Align.CENTER)
                overlay.set_child(dl_btn)
                overlay.add_overlay(dl_pbar)

                inst_btn.connect("clicked", self.on_utility_install_clicked, utility, file_name)
                stack.add_named(overlay, "download")

            else:  # Flatpak & Nexus downloads (NOMM does not handle the download process for these)
                dl_btn.connect("clicked", self.on_utility_download_clicked, utility, stack)
                stack.add_named(dl_btn, "download")

            dl_btn.set_valign(Gtk.Align.FILL)

            stack.add_named(inst_btn, "install")

            if staging_dir.exists():  # standard install, already installed
                stack.set_visible_child_name("install")
                inst_btn.set_label(_("Reinstall"))
            elif utility["source_type"] not in ["flatpak", "nexus"] and local_zip_path.exists():  # standard install, downloaded but not installed
                stack.set_visible_child_name("install")
                inst_btn.set_label(_("Install"))
                inst_btn.add_css_class("suggested-action")
            else:  # standard/flatpak install, not downloaded
                stack.set_visible_child_name("download")
                if self.get_flatpak_installation_status(utility):  # flatpak install, already installed
                    dl_btn.set_sensitive(False)
                    dl_btn.set_label(_("Installed"))

            row.add_suffix(stack)
            list_box.append(row)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_child(list_box)
        self.append(scrolled)

        # Load Order Button
        load_order_rel = self.dashboard.game_info.get("load_order_path")
        if load_order_rel:
            btn_container = Gtk.CenterBox(margin_top=20, margin_bottom=20)
            load_order_btn = Gtk.Button(label=_("Edit Load Order"), css_classes=["pill"])
            load_order_btn.set_size_request(200, 40)
            load_order_btn.set_cursor_from_name("pointer")
            load_order_btn.connect("clicked", self.dashboard.load_text_file, Path(self.dashboard.game_path) / load_order_rel)
            btn_container.set_center_widget(load_order_btn)
            self.append(btn_container)

    def get_flatpak_installation_status(self, util):
        """Returns True if the flatpak is installed, False if not Flatpak type or not installed"""
        if util.get("source_type") != "flatpak":
            return False
        package_name = util.get("source_url").replace("appstream://", "")
        package_data_path = os.path.expanduser("~/.var/app/") + package_name
        if os.path.exists(package_data_path):
            return True
        else:
            return False

    def on_utility_download_clicked(self, btn, util, stack, pbar=None, file_name=None):
        source_url = util.get("source_url")
        source_type = util.get("source_type")
        if not source_url:
            return

        if source_type == "flatpak" or source_type == "nexus":
            # if it's type flatpak or nexus, NOMM doesn't handle the downloads itself
            launcher = Gtk.UriLauncher.new(source_url)
            launcher.launch(None, None, None)
            return

        btn.set_sensitive(False)
        btn.add_css_class('btn-download-before')

        util_dir = os.path.join(self.dashboard.downloads_path, "utilities")

        def on_download_progress(downloader_inst, download_data):
            updated_file_name = download_data['file_name']
            if updated_file_name == file_name:
                self.download_maps[file_name].set_visible(True)
                self.download_maps[updated_file_name].set_fraction(download_data['progress'])

        def on_download_finished(downloader_inst, finished_file_name):
            if finished_file_name == file_name:
                stack.set_visible_child_name("install")
                btn.set_sensitive(True)
                self.download_maps[file_name].set_visible(False)

        def on_download_error(downloader_inst, e):
            self.dashboard.show_message(_("Download Failed"), str(e.get('error')))
            btn.set_sensitive(True)

        self.downloader.connect('progress-changed', on_download_progress)
        self.downloader.connect('download-complete', on_download_finished)
        self.downloader.connect('download-error', on_download_error)

        threading.Thread(target=self.downloader.download_mod, args=(source_url, util_dir), daemon=True).start()

    def on_utility_install_clicked(self, btn, util: dict, file_name):
        # Base warning message
        msg = _("This process may replace existing game files. Please ensure you have backed up your game directory before proceeding.")

        dialog = Adw.MessageDialog(
            transient_for=self.dashboard.app.win,
            heading=_("Confirm Installation")
        )

        dialog.set_default_size(500, -1)

        # Container for the body content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Primary warning label
        warning_label = Gtk.Label(label=msg, wrap=True, xalign=0)
        content_box.append(warning_label)

        # Check if launch_options exist in the util dict
        launch_options = util.get("launch_options")
        if launch_options:
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator.set_margin_top(8)
            separator.set_margin_bottom(8)
            content_box.append(separator)

            # Additional instruction text
            instruction_text = _("This utility requires the game to have extra launch options.\n"
                                 "NOMM is able to add these for you but <b>Steam needs to be turned off</b>.")
            instruction_label = Gtk.Label(label=instruction_text, wrap=True, xalign=0)
            instruction_label.set_use_markup(True)
            content_box.append(instruction_label)

            # The code box with copy button
            code_bin = Adw.Bin()
            code_bin.add_css_class("card")  # Gives it the boxed look

            code_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            code_box.set_margin_start(12)
            code_box.set_margin_end(6)
            code_box.set_margin_top(6)
            code_box.set_margin_bottom(6)

            options_label = Gtk.Label(label=launch_options, selectable=True, xalign=0)
            options_label.add_css_class("monospace")

            copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
            copy_btn.set_tooltip_text(_("Copy to Clipboard"))
            copy_btn.add_css_class("flat")
            copy_btn.connect("clicked", self.dashboard.app.copy_to_clipboard, launch_options)

            code_box.append(options_label)
            code_box.set_hexpand(True)
            options_label.set_hexpand(True)
            code_box.append(copy_btn)

            code_bin.set_child(code_box)
            content_box.append(code_bin)

        # Set the custom box as the extra child of the dialog
        dialog.set_extra_child(content_box)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("install", _("Continue"))
        dialog.set_response_appearance("install", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "install":
                self.execute_utility_install(util, file_name)
            d.close()

        dialog.connect("response", on_response)
        dialog.present()

    def execute_utility_install(self, util, file_name):

        deploy_essential_utility(util, self.dashboard.downloads_path, self.dashboard.staging_path,
                                 self.dashboard.game_path, self.dashboard.app.steam_base, self.dashboard.app_id, file_name)

        self.dashboard.show_message(
            _("Success"),
            _("{} has been installed.").format(util.get('name'))
        )
