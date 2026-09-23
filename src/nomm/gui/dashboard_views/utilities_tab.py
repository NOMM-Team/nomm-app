
import gettext
import os
import threading
import webbrowser
from pathlib import Path
from gi.repository import Adw, Gtk, Gio, GLib, Gdk

from nomm.gui.ui_builders import create_text_box, create_code_box, create_icon_button
from nomm.core.utility_manager import deploy_essential_utility, remove_utility, get_utility_status, \
                                      launch_utility, get_downloaded_utility_file_name
from nomm.core.tools import get_latest_github_release_asset_url
from nomm.core.wine_manager import get_wine, WINE_BINARY_PATH, check_wineprefix_setup, generate_winetrick_command

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
        self.download_dir = Path(self.dashboard.downloads_path) / "utilities"
        self.setup_folder_monitor()
        self.populate_list()

    def setup_folder_monitor(self):
        f = Gio.File.new_for_path(str(self.download_dir))
        self.monitor = f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_utilities_downloads_folder_changed)

    def on_utilities_downloads_folder_changed(self, monitor, file, other_file, event_type):
        if event_type == Gio.FileMonitorEvent.CREATED:
            GLib.idle_add(self.populate_list)

    def populate_list(self):

        while child := self.get_first_child():
            self.remove(child)
        self.download_maps.clear()

        utility_groups: list[dict] = self.dashboard.game_info.get("utilities", [])
        list_box = Gtk.ListBox(css_classes=["dashboard-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.set_overflow(Gtk.Overflow.HIDDEN)

        action_btn_sizegroup = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        for utility in utility_groups:
            row = Adw.ActionRow(title=utility["name"], subtitle=utility["creator"])

            REQUIRED_FIELDS = ["name", "creator", "creator_link", "source_type", "source_url",
                               "executable_type", "deploy_to_game_files"]
            missing_fields = set(REQUIRED_FIELDS) - utility.keys()
            if missing_fields:
                print(f"[!] Missing required utility fields: {missing_fields}")
                if "name" in utility:
                    print(f"[!] Skipping utility: {utility["name"]}")
                else:
                    print("[!] Skipping utility")

            if utility.get("creator_donation_link"):
                row.add_prefix(create_icon_button(
                    icon_name="mat-donate-symbolic",
                    tooltip="Donate to creator",
                    on_click=lambda b, link=utility["creator_donation_link"]: webbrowser.open(link)
                ))

            row.add_prefix(create_icon_button(
                icon_name="mat-attribution-symbolic",
                tooltip="Open creator profile",
                on_click=lambda b, link=utility["creator_link"]: webbrowser.open(link)
            ))

            # Version badge
            version_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            version_badge.set_valign(Gtk.Align.CENTER)
            version_badge.set_margin_end(15)

            v_label = Gtk.Label(label=str(utility["version"]))
            v_label.add_css_class("badge-action-row")

            version_badge.append(v_label)
            row.add_suffix(version_badge)

            staging_dir = Path(self.dashboard.staging_path) / "utilities" / utility["name"]

            stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

            # Game Launch options button
            if utility.get("launch_options"):
                row.add_suffix(create_icon_button(
                    icon_name="mat-launch-symbolic",
                    tooltip=_("Required launch options"),
                    on_click=lambda btn: self.on_utility_launch_options_clicked(utility.get("launch_options"))
                ))

            # Launch utility button
            if utility.get("executable_type") != "non-exec":
                launch_utility_button = create_icon_button(
                    icon_name="mat-play-symbolic",
                    tooltip=_("This is an executable utility, but it is not installed yet"),
                    on_click=lambda btn: self.on_launch_button_clicked(utility, staging_dir),
                    disabled=True
                )
                row.add_suffix(launch_utility_button)

            # Download & install buttons
            dl_btn = Gtk.Button(label=_("Download"), css_classes=["suggested-action"], halign=Gtk.Align.FILL, valign=Gtk.Align.CENTER)
            dl_btn.set_cursor_from_name("pointer")
            inst_btn = Gtk.Button(halign=Gtk.Align.FILL, valign=Gtk.Align.CENTER)
            inst_btn.set_cursor_from_name("pointer")

            if utility["source_type"] == "github":
                utility["source_url"] = get_latest_github_release_asset_url(utility["source_url"], utility["github_asset_regex"])

            file_name = get_downloaded_utility_file_name(utility, self.download_dir)
            inst_btn.connect("clicked", self.on_utility_install_clicked, utility, file_name)

            if utility["source_type"] in ["direct", "github"]:

                current_ratio = None
                if file_name in self.download_maps:
                    current_ratio = self.download_maps[file_name].get_fraction()

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
                overlay.set_child(dl_btn)
                overlay.add_overlay(dl_pbar)

                stack.add_named(overlay, "download")

            else:  # Flatpak & Nexus downloads (NOMM does not handle the download process directly for these)
                dl_btn.connect("clicked", self.on_utility_download_clicked, utility, stack)
                stack.add_named(dl_btn, "download")

            stack.add_named(inst_btn, "install")

            current_utility_status = get_utility_status(utility, self.download_dir, staging_dir, utility_groups)
            if current_utility_status == "installed":
                stack.set_visible_child_name("install")
                inst_btn.set_label(_("Reinstall"))
                launch_utility_button.set_sensitive(True)
                launch_utility_button.set_tooltip_text(f"Launch {utility["name"]}")
            elif current_utility_status == "to_install":
                stack.set_visible_child_name("install")
                inst_btn.set_label(_("Install"))
                inst_btn.add_css_class("suggested-action")
            elif current_utility_status == "to_download":
                stack.set_visible_child_name("download")
            elif current_utility_status == "blocked":
                dl_btn.set_sensitive(False)
                dl_btn.set_label(_("Blocked"))
                dl_btn.set_tooltip_text(_("This utility can not be installed because it is incompatible with another installed utility."))

            action_btn_sizegroup.add_widget(stack)
            row.add_suffix(stack)
            if current_utility_status in ["installed", "to_install"] and utility["source_type"] != "flatpak":
                row.add_suffix(create_icon_button(
                    icon_name="mat-delete-forever-symbolic",
                    css_classes=["destructive-action"],
                    tooltip=_("Fully remove utility, this affects:\n"
                              "- The downloaded archive file,\n"
                              "- Any staged files,\n"
                              "- Any files copied to the game directory"),
                    on_click=lambda btn: self.on_utility_remove_clicked(utility, staging_dir, file_name)
                ))
            else:
                row.add_suffix(create_icon_button(
                    icon_name="mat-delete-symbolic",
                    tooltip=_("Nothing to delete"),
                    hover_mouse_pointer=False,
                    disabled=True
                ))

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

    def on_utility_remove_clicked(self, utility: dict, staging_dir: Path, file_name: str):
        remove_utility(utility, self.download_dir, staging_dir, self.dashboard.game_path, file_name)
        self.populate_list()

    def on_launch_button_clicked(self, utility: dict, staging_dir: Path):
        # staging_metadata = load_yaml(self.dashboard.staging_metadata_path)

        if utility["executable_type"] == "windows":
            if not os.path.exists(WINE_BINARY_PATH):
                self.show_wine_setup_screen(utility, staging_dir)
                return
            elif utility.get("wine_verbs") and not check_wineprefix_setup(utility["name"]):
                self.show_winetricks_setup_screen(utility)
                return
        launch_utility(utility, staging_dir, self.dashboard.staging_metadata_path, self.dashboard.headers)

    def show_wine_setup_screen(self, utility: dict, staging_dir: Path):
        dialog = Adw.MessageDialog(transient_for=self.dashboard.app.win, heading=_("Wine Setup"))

        status_page = Adw.StatusPage(icon_name="wine-logo")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        instruction_text = _(f"{utility["name"]} is a Windows executable that requires a conversion layer such as Wine.\n"
                             "NOMM will download Wine for you (~100MB). The utility will be launched as soon as the setup is done.")
        instruction_label = Gtk.Label(label=instruction_text, wrap=True, xalign=0)
        content_box.append(instruction_label)

        status_page.set_child(content_box)
        dialog.set_extra_child(status_page)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("continue", _("Continue"))
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response_id):
            if response_id == "continue":
                get_wine()
            if utility.get("wine_verbs") and not check_wineprefix_setup(utility["name"]):
                self.show_winetricks_setup_screen(utility)
            else:
                launch_utility(utility, staging_dir, self.dashboard.staging_metadata_path, self.dashboard.headers)
        dialog.connect("response", on_response)
        dialog.present()

    def show_winetricks_setup_screen(self, utility: dict):
        dialog = Adw.MessageDialog(transient_for=self.dashboard.app.win, heading=_("Wineprefix Setup"))

        status_page = Adw.StatusPage(icon_name="wine-logo")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        info_text = "This step requires <b>Winetricks</b> installed, click here to find out how to install it for your system."
        content_box.append(create_text_box(info_text, "info", "https://github.com/winetricks/winetricks#installing"))

        winetrick_instructions_text = _(f"{utility["name"]} requires specific dependencies (verbs) to be installed in its Wine prefix,\n"
                                        "please run the following command in your terminal:")
        content_box.append(Gtk.Label(label=winetrick_instructions_text))
        content_box.append(create_code_box(generate_winetrick_command(utility["name"], utility["wine_verbs"]), True))

        status_page.set_child(content_box)
        dialog.set_extra_child(status_page)
        dialog.add_response("close", _("Close"))
        dialog.set_response_appearance("close", Adw.ResponseAppearance.SUGGESTED)
        dialog.present()

    def on_utility_launch_options_clicked(self, launch_options):
        dialog = Adw.MessageDialog(
            transient_for=self.dashboard.app.win,
            default_width=400,
            heading=_("Game Launch Options")
        )

        status_page = Adw.StatusPage(icon_name="mat-launch-symbolic")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        instruction_text = _(f"This utility requires {self.dashboard.game_name} to have extra launch options to work correctly.")
        if self.dashboard.platform == "steam":
            copy_text = _("Open Steam properties")
        else:
            copy_text = _("Copy options")
        instruction_label = Gtk.Label(label=instruction_text, wrap=True, xalign=0)
        instruction_label.set_use_markup(True)
        content_box.append(instruction_label)

        content_box.append(create_code_box(launch_options, True))
        status_page.set_child(content_box)
        dialog.set_extra_child(status_page)

        dialog.add_response("close", _("Close"))
        dialog.add_response("copy", copy_text)
        dialog.set_response_appearance("copy", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response_id):
            if response_id == "copy":
                Gdk.Display.get_default().get_clipboard().set(launch_options)
                if self.dashboard.platform == "steam":
                    launcher = Gtk.UriLauncher.new(f"steam://gameproperties/{self.dashboard.app_id}")
                    launcher.launch(None, None, None)
            else:
                d.close()
        dialog.connect("response", on_response)
        dialog.present()

    def on_utility_download_clicked(self, btn, util: dict, stack, pbar=None, file_name=None):
        source_type = util["source_type"]
        source_url = util["source_url"]
        if not source_url:
            return

        if source_type == "flatpak":
            # if it's type flatpak or nexus, NOMM doesn't handle the downloads itself
            launcher = Gtk.UriLauncher.new(source_url)
            launcher.launch(None, None, None)
            return
        elif source_type == "nexus":
            self.show_nexus_download_instructions(util)
            return

        btn.set_sensitive(False)
        btn.add_css_class('btn-download-before')

        def on_download_progress(downloader_inst, download_data):
            updated_file_name = download_data['filename']
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

        threading.Thread(target=self.downloader.download_mod, args=(source_url, self.download_dir), daemon=True).start()

    def show_nexus_download_instructions(self, util: dict):
        dialog = Adw.MessageDialog(
            transient_for=self.dashboard.app.win,
            default_width=400,
            heading=_("Nexus Source Instructions")
        )

        status_page = Adw.StatusPage(icon_name="nexus-logo")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        info_text = _("If the Nexus mod page supports auto-download, then "
                      "you just need to click on download with vortex / mod manager")
        content_box.append(create_text_box(info_text, "info"))

        instruction_text = _(f"{util["name"]} is sourced from the Nexus Mods website.\n"
                             "You will have to place the downloaded file in the right location for NOMM to "
                             "proceed with the installation.")
        content_box.append(Gtk.Label(label=instruction_text, wrap=True, xalign=0))

        nexus_btn = Gtk.Button(label=_("Open Nexus Mods page"), css_classes=["suggested-action"])
        nexus_btn.set_tooltip_text(_(f"Open the Nexus Mods page for {util["name"]}"))
        nexus_btn.connect("clicked", lambda *_: on_nexus_button_clicked())
        dl_folder_btn = Gtk.Button(label=_("Open NOMM downloads directory"))
        dl_folder_btn.set_tooltip_text(_("This is where you need to place the downloaded file for NOMM to recognise it"))
        dl_folder_btn.connect("clicked", lambda *_: webbrowser.open(self.download_dir.as_uri()))
        content_box.append(nexus_btn)
        content_box.append(dl_folder_btn)

        status_page.set_child(content_box)
        dialog.set_extra_child(status_page)

        dialog.add_response("close", _("Close"))

        def on_nexus_button_clicked():
            launcher = Gtk.UriLauncher.new(util["source_url"])
            launcher.launch(None, None, None)
            nexus_btn.remove_css_class("suggested-action")
            dialog.set_response_appearance("close", Adw.ResponseAppearance.SUGGESTED)

        dialog.present()

    def on_utility_install_clicked(self, btn, util: dict, file_name):

        if not util["deploy_to_game_files"]:
            # No need to show warning when game files are not modified
            self.execute_utility_install(util, file_name)
            return

        dialog = Adw.MessageDialog(
            transient_for=self.dashboard.app.win,
            heading=_("Confirm Installation")
        )

        dialog.set_default_size(400, -1)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        msg = _("This process may replace existing game files. These will be backed up by NOMM to avoid being overwritten. "
                "You will be able to restore them automatically later by removing the utility with the delete button.")
        warning_label = Gtk.Label(label=msg, wrap=True, xalign=0)
        content_box.append(warning_label)

        dialog.set_extra_child(content_box)

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("install", _("Continue"))
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response_id):
            if response_id == "install":
                self.execute_utility_install(util, file_name)
            d.close()

        dialog.connect("response", on_response)
        dialog.present()

    def execute_utility_install(self, util, file_name):

        deploy_essential_utility(util, self.dashboard.downloads_path, self.dashboard.staging_path,
                                 self.dashboard.game_path, file_name)
        self.show_utility_installation_success_screen(util)
        self.populate_list()

    def show_utility_installation_success_screen(self, util):
        status_page = Adw.StatusPage(
            title=_("Installation Successful"),
            description=f"{util['name']} was successfully installed!",
            icon_name="mat-folder-check-symbolic"
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)

        if util.get("final_instructions"):
            warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, halign=Gtk.Align.CENTER)
            warning_box.add_css_class("warning-card")
            warning_label = Gtk.Label(
                wrap=True, max_width_chars=50, justify=Gtk.Justification.CENTER
            )
            warning_label.set_use_markup(True)
            warning_label.set_markup(util["final_instructions"])
            warning_box.append(warning_label)
            vbox.append(warning_box)

        action_btn = Gtk.Button(margin_top=12, halign=Gtk.Align.CENTER)
        if util.get("launch_options"):
            action_btn.set_label(_("Continue"))
            action_btn.connect("clicked", lambda btn: self.on_utility_launch_options_clicked(util["launch_options"]))
        else:
            action_btn.set_label(_("Close"))
        action_btn.add_css_class("suggested-action")

        vbox.append(action_btn)
        status_page.set_child(vbox)

        # Create a parent dialog window to display the status page
        dialog = Adw.Window(
            transient_for=self.dashboard.app.win,
            modal=True,
            default_width=400,
            title=_("Installation Complete")
        )

        # Close the dialog when Continue is clicked
        action_btn.connect("clicked", lambda btn: dialog.close())

        dialog.set_content(status_page)
        dialog.present()
