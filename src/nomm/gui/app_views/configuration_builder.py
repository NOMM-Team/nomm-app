import gi
import gettext
import os
from nomm.platforms.steam import get_installed_steam_games, get_art
from nomm.core.user_config import CUSTOM_GAME_CONFIG_PATH
from nomm.core.tools import write_yaml
from nomm.gui.text_window import TextWindow

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Gdk  # noqa: E402

_ = gettext.gettext


class PlatformChoiceDialog(Adw.MessageDialog):
    """Initial dialog asking if the game is installed and on which platform."""

    def __init__(self, parent_window, app, callback):
        super().__init__(transient_for=parent_window)
        self.callback = callback
        self.app = app
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.set_extra_child(self.stack)
        self.stack.set_size_request(580, 785)
        self.show_builder_intro()

    def remove_stack_child(self, name):
        child = self.stack.get_child_by_name(name)
        if child:
            self.stack.remove(child)

    def show_builder_intro(self):
        self.remove_stack_child("app-builder-intro")
        status_page = Adw.StatusPage(
            title=_("NOMM Configuration Builder"),
            description=_("This utility allows you to add support to any game you want, easily. \n"
                          "This does not mean that NOMM is compatible with 100% of games, "
                          "NOMM simply has a suite of features that can help you mod as much as possible. "
                          "It is up to you to make sure that NOMM will be able to help mod the game you want to mod."),
            icon_name="nomm-logo"
        )
        status_page.add_css_class("setup-page")

        btn = Gtk.Button(label="Start configuring")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(24)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", self.show_customisation_starter)

        status_page.set_child(btn)
        self.stack.add_named(status_page, "app-builder-intro")
        self.stack.set_visible_child_name("app-builder-intro")
        GLib.timeout_add(100, lambda: status_page.add_css_class("visible"))

    def show_customisation_starter(self, button=None):
        self.remove_stack_child("app_builder_starter")

        status_page = Adw.StatusPage(
            title=_("How do you want to start building?"),
            description=_("Please choose how you would like to start building your configuration.\n"
                          "You can either start from scratch or with some fields pre-filled."),
            icon_name="add-configuration-symbolic"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, halign=Gtk.Align.CENTER)
        content_box.set_margin_top(12)
        cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16, halign=Gtk.Align.CENTER)

        selected_starter = {"name": None}

        # Group buttons together so selecting one unchecks the others (Radio functionality)
        group_button = None

        options = [
            {
                "name": "Steam",
                "icon": "steam-logo",
                "text": "Start building from a Steam game that is already installed on your system.\n"
                        "Some configuration fields will be pre-filled for your convenience."
            },
            {
                "name": "GOG",
                "icon": "gog-logo-symbolic",
                "text": "Starting from a GOG game is not implemented yet, but will be soon!\n"
                        "We apologise for the inconvenience."
            },
            {
                "name": "Epic",
                "icon": "epic-logo",
                "text": "Starting from an Epic game is not implemented yet, but will be soon!\n"
                        "We apologise for the inconvenience."
            },
            {
                "name": "Custom",
                "icon": "mat-edit-document-symbolic",
                "text": "Start building from scratch.\n"
                        "No fields will be pre-filled."
            }
        ]

        # Dynamic description label positioned above the action button
        desc_label = Gtk.Label(
            label="\n",
            wrap=True,
            justify=Gtk.Justification.CENTER,
            max_width_chars=50,
        )
        desc_label.add_css_class("dim-label")

        for starter in options:

            # Container for each emulator option card
            starter_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER)
            starter_card.set_margin_start(12)
            starter_card.set_margin_end(12)
            starter_card.set_margin_top(12)
            starter_card.set_margin_bottom(12)

            starter_logo = Gtk.Image.new_from_icon_name(starter["icon"])
            starter_logo.set_pixel_size(100)
            starter_label = Gtk.Label(label=starter["name"], css_classes=["title-4"])

            starter_card.append(starter_logo)
            starter_card.append(starter_label)

            # Toggle Button wrapper to make the card clickable
            btn = Gtk.ToggleButton()
            btn.set_child(starter_card)
            btn.add_css_class("card")  # Gives it a nice Libadwaita rounded card border

            # Radio-button behavior setup
            if group_button is None:
                group_button = btn
            else:
                btn.set_group(group_button)

            # Update selection state when clicked
            def on_toggled(button, name=starter["name"], text=starter["text"], icon=starter["icon"]):
                if button.get_active():
                    selected_starter["name"] = name
                    selected_starter["icon"] = icon
                    desc_label.set_text(text)

                if name in ["GOG", "Epic"]:
                    cont_btn.set_sensitive(False)
                else:
                    cont_btn.set_sensitive(True)

            btn.connect("toggled", on_toggled)
            cards_box.append(btn)

        content_box.append(cards_box)

        cont_btn = Gtk.Button(label=_("Continue"), halign=Gtk.Align.CENTER, width_request=160)
        cont_btn.add_css_class("suggested-action")
        cont_btn.set_sensitive(False)

        def on_continue_clicked(btn):
            if selected_starter["name"] == "Custom":
                self.close()
                self.callback({})
            else:
                self.starter_game_picker(selected_starter)

        cont_btn.connect("clicked", on_continue_clicked)
        content_box.append(desc_label)
        content_box.append(cont_btn)

        status_page.set_child(content_box)

        self.stack.add_named(status_page, "app_builder_starter")
        self.stack.set_visible_child_name("app_builder_starter")

    def starter_game_picker(self, platform: dict):
        self.remove_stack_child("starter_game_picker")
        if platform["name"] == "Steam":
            installed_games = get_installed_steam_games(self.app.game_libraries)
            game_names: list[str] = [game['name'] for game in installed_games]
        status_page = Adw.StatusPage(
            title=_("Select your game"),
            description=_("Please select the game you want to build a configuration for"),
            icon_name=platform["icon"]
        )
        content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            halign=Gtk.Align.CENTER,
        )
        content_box.set_margin_top(12)

        bg_picture = Gtk.Picture()
        bg_picture.set_content_fit(Gtk.ContentFit.COVER)
        bg_picture.set_opacity(0.3)
        bg_picture.set_hexpand(False)
        bg_picture.set_vexpand(False)
        bg_picture.set_size_request(-1, 250)
        bg_picture.set_halign(Gtk.Align.FILL)
        bg_picture.set_valign(Gtk.Align.CENTER)

        string_list = Gtk.StringList.new(game_names)

        expression = Gtk.PropertyExpression.new(
            Gtk.StringObject, None, "string"
        )

        dropdown = Gtk.DropDown.new(string_list, expression)
        dropdown.set_enable_search(True)
        content_box.append(dropdown)

        cont_btn = Gtk.Button(
            label=_("Continue"), halign=Gtk.Align.CENTER, width_request=160
        )
        cont_btn.add_css_class("suggested-action")

        def on_game_selection_changed(dropdown, param):
            selected_idx = dropdown.get_selected()
            if (
                selected_idx != Gtk.INVALID_LIST_POSITION
                and selected_idx < len(installed_games)
            ):
                selected_game = installed_games[selected_idx]
                app_id = selected_game.get("appid")
                art = get_art(self.app.steam_base, app_id)
                if art and "poster" in art:
                    bg_picture.set_filename(art["poster"])
                    return
            bg_picture.set_filename(None)

        dropdown.connect("notify::selected", on_game_selection_changed)
        if installed_games:
            on_game_selection_changed(dropdown, None)

        def on_continue_clicked(btn):
            selected_idx = dropdown.get_selected()
            if (
                selected_idx != Gtk.INVALID_LIST_POSITION
                and selected_idx < len(installed_games)
            ):
                selected_game = installed_games[selected_idx]
                prefilled_data = {
                    "name": selected_game.get("name", ""),
                    "steam_id": str(selected_game.get("appid", "")),
                    "steam_folder_name": selected_game.get("installdir", "")
                }
                self.close()
                if self.callback:
                    self.callback(prefilled_data)

        cont_btn.connect("clicked", on_continue_clicked)
        content_box.append(cont_btn)

        status_page.set_child(content_box)

        overlay = Gtk.Overlay()
        overlay.set_child(bg_picture)
        overlay.add_overlay(status_page)

        self.stack.add_named(overlay, "starter_game_picker")
        self.stack.set_visible_child_name("starter_game_picker")


class ConfigurationBuilderWindow(Adw.Window):
    """Main configuration builder window featuring custom toggle button tabs."""

    def __init__(self, parent_window, app, initial_data: dict | None = None):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_title(_("Configuration Builder"))
        self.set_default_size(700, 600)
        self.app = app

        # Main layout container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header Bar
        header = Adw.HeaderBar()
        main_box.append(header)

        # Custom Tab Buttons Container
        tab_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True
        )

        self.game_info_btn = Gtk.ToggleButton(
            label=_("Game Info"), css_classes=["overlay-tab"]
        )
        self.game_info_btn.set_cursor_from_name("pointer")
        tab_container.append(self.game_info_btn)

        self.modding_info_btn = Gtk.ToggleButton(
            label=_("Modding Paths"), css_classes=["overlay-tab"]
        )
        self.modding_info_btn.set_cursor_from_name("pointer")
        self.modding_info_btn.set_group(self.game_info_btn)
        tab_container.append(self.modding_info_btn)

        self.utilities_btn = Gtk.ToggleButton(
            label=_("Utilities"), css_classes=["overlay-tab"]
        )
        self.utilities_btn.set_cursor_from_name("pointer")
        self.utilities_btn.set_group(self.game_info_btn)
        tab_container.append(self.utilities_btn)

        main_box.append(tab_container)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_vexpand(True)

        self.game_info_view = self._build_game_info_tab(initial_data or {})
        self.modding_info_view = self._build_modding_paths_tab()
        self.utilities_view = self._build_utilities_tab()

        self.stack.add_named(self.game_info_view, "game_info")
        self.stack.add_named(self.modding_info_view, "modding_info")
        self.stack.add_named(self.utilities_view, "utilities")

        main_box.append(self.stack)

        def _on_tab_toggled(btn, stack_name):
            if btn.get_active():
                self.stack.set_visible_child_name(stack_name)

        self.game_info_btn.connect("toggled", _on_tab_toggled, "game_info")
        self.modding_info_btn.connect("toggled", _on_tab_toggled, "modding_info")
        self.utilities_btn.connect("toggled", _on_tab_toggled, "utilities")

        self.game_info_btn.set_active(True)

        action_bar = Gtk.ActionBar()
        self.continue_btn = Gtk.Button(label=_("Save"))
        self.continue_btn.add_css_class("suggested-action")
        self.continue_btn.connect("clicked", self._on_save_clicked)
        action_bar.pack_end(self.continue_btn)
        main_box.append(action_bar)

    def _build_game_info_tab(self, initial_data: dict) -> Gtk.Widget:
        """Builds the Game Information form tab view."""
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page_box.set_margin_top(16)
        page_box.set_margin_bottom(16)
        page_box.set_margin_start(16)
        page_box.set_margin_end(16)

        preferences_group = Adw.PreferencesGroup(
            title=_("General Game Information"),
            description=_("Provide details on the target game.\n"
                          "Technically the only required field is the name, but please try and fill as many fields as you can."),
        )

        self.name_row = Adw.EntryRow(title=_("Game Title *"))
        self.name_row.set_text(str(initial_data.get("name", "")))
        self.name_row.set_tooltip_text(_("The full name of the game, as it shows up on game stores. Do NOT remove any numbers, spaces or symbols."))
        preferences_group.add(self.name_row)

        self.steam_id_row = Adw.EntryRow(title=_("Steam App ID"))
        self.steam_id_row.set_text(str(initial_data.get("steam_id", "")))
        self.steam_id_row.set_tooltip_text(_("The standard, numerical, Steam app ID. Can be looked up on SteamDB or on the game's store page URL."))

        def _on_steam_id_changed(entry):
            text = entry.get_text()
            filtered = "".join(c for c in text if c.isdigit())
            if text != filtered:
                entry.set_text(filtered)

        self.steam_id_row.connect("changed", _on_steam_id_changed)
        preferences_group.add(self.steam_id_row)

        self.steam_folder_row = Adw.EntryRow(title=_("Steam Folder Name"))
        self.steam_folder_row.set_text(str(initial_data.get("steam_folder_name", "")))
        self.steam_folder_row.set_tooltip_text(_("The Steam folder name that can be seen in the steamapps/common folder"))
        preferences_group.add(self.steam_folder_row)

        self.gog_id_row = Adw.EntryRow(title=_("GOG Game ID"))
        self.gog_id_row.set_text(str(initial_data.get("gog_id", "")))
        self.gog_id_row.set_tooltip_text(_("The GOG ID of the game, if the game is sold on GOG"))
        preferences_group.add(self.gog_id_row)

        self.nexus_id_row = Adw.EntryRow(title=_("Nexus ID"))
        self.nexus_id_row.set_tooltip_text(_("The Nexus ID of the game, if the game has a page on the Nexus Mods platform"))
        preferences_group.add(self.nexus_id_row)

        self.color_row = Adw.ActionRow(title=_("Accent Color"))
        self.color_dialog = Gtk.ColorDialog()
        self.color_button = Gtk.ColorDialogButton(dialog=self.color_dialog)
        self.color_row.set_tooltip_text(_("A colour that represents the game's art. This is used when the 'Per Game Accent Colour' option is enabled. "
                                          "The accent colour of NOMM will switch to this colour when the game is being modded."))

        initial_color = "#3584e4"
        rgba = Gdk.RGBA()
        if not rgba.parse(initial_color):
            rgba.parse("#3584e4")
        self.color_button.set_rgba(rgba)

        self.color_row.add_suffix(self.color_button)
        preferences_group.add(self.color_row)

        self.wiki_link_row = Adw.EntryRow(title=_("Wiki URL"))
        self.wiki_link_row.set_text(str(initial_data.get("wiki_link", "")))
        self.wiki_link_row.set_tooltip_text(_("If you plan to create a wiki page on the NOMM wiki to help users mod this game, "
                                              "you can add the link to it here."))
        preferences_group.add(self.wiki_link_row)

        page_box.append(preferences_group)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(page_box)
        scrolled.set_vexpand(True)
        return scrolled

    def _build_modding_paths_tab(self) -> Gtk.Widget:
        """Builds the Modding Paths configuration tab."""
        self.modding_groups_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )

        # Main scrollable view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)

        header_group = Adw.PreferencesGroup(
            title=_("Modding Paths Configuration"),
            description=_("Define the locations where mods will be deployed to.\n"
                          "There has to be at least one path group, but you can add more if you want."),
        )
        main_box.append(header_group)

        main_box.append(self.modding_groups_container)

        # Add Path Group Button
        add_btn = Gtk.Button(label=_("Add Modding Path"))
        add_btn.add_css_class("pill")
        add_btn.set_halign(Gtk.Align.CENTER)
        add_btn.set_cursor_from_name("pointer")
        add_btn.connect("clicked", lambda _: self._add_modding_path_group())
        main_box.append(add_btn)

        scrolled.set_child(main_box)

        # Populate default group
        default_data = {
            "name": "Default path",
            "description": "The default path where mods will be extracted to",
            "base": "{game_path}",
            "path": "/",
        }
        self._add_modding_path_group(default_data, is_first=True)

        return scrolled

    def _add_modding_path_group(
        self, data: dict | None = None, is_first: bool = False
    ) -> None:
        """Creates and appends a triplet path configuration row group."""
        data = data or {"name": "", "description": "", "base": "{game_path}", "path": ""}

        group = Adw.PreferencesGroup()

        # Name Row
        name_row = Adw.EntryRow(title=_("Path Identifier *"))
        name_row.set_text(data.get("name", ""))
        name_row.set_tooltip_text(_("When multiple paths are defined, this will be the name of the path that will be shown to users in the UI"))
        group.add(name_row)

        # Description Row
        desc_row = Adw.EntryRow(title=_("Description *"))
        desc_row.set_text(data.get("description", ""))
        desc_row.set_tooltip_text(_("When multiple paths are defined, this will be the description visible to help users "
                                    "understand which path they should select for the mod they are installing"))
        group.add(desc_row)

        # Combined Path Row (Dropdown prefix + Entry path)
        path_row = Adw.ActionRow(title=_("Path *"))
        path_row.set_tooltip_text(_("The deployment path has to start either at the root of the installed game files (most often it's this one), "
                                    "or in the user data (ex. Steam compatdata folder). Pick one of the two and then set the rest of the path."))

        base_combo = Gtk.DropDown.new_from_strings(
            [_("Game Installation Path"), _("User Data Path")]
        )
        base_combo.set_valign(Gtk.Align.CENTER)

        if data.get("base") == "{user_data}":
            base_combo.set_selected(1)
        else:
            base_combo.set_selected(0)

        path_entry = Gtk.Entry(placeholder_text="/")
        path_entry.set_hexpand(True)
        path_entry.set_valign(Gtk.Align.CENTER)
        path_entry.set_text(data.get("path", ""))

        path_row.add_suffix(base_combo)
        path_row.add_suffix(path_entry)
        group.add(path_row)

        if not is_first:  # Only add the delete button if it's NOT the first group
            delete_btn = Gtk.Button(
                icon_name="mat-delete-symbolic",
                css_classes=["flat", "destructive-action"],
            )
            delete_btn.set_tooltip_text(_("Remove Path"))
            delete_btn.set_cursor_from_name("pointer")

            def _on_delete(_):
                self.modding_groups_container.remove(group)

            delete_btn.connect("clicked", _on_delete)
            group.set_header_suffix(delete_btn)

        group.widgets = {
            "name_row": name_row,
            "desc_row": desc_row,
            "base_combo": base_combo,
            "path_entry": path_entry,
        }

        self.modding_groups_container.append(group)

    def _update_modding_delete_buttons(self) -> None:
        """Ensures at least 1 path group remains by toggling delete button sensitivity."""
        children = []
        child = self.modding_groups_container.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()

        can_delete = len(children) > 1
        for grp in children:
            if hasattr(grp, "widgets"):
                grp.widgets["delete_btn"].set_sensitive(can_delete)

    def _build_utilities_tab(self) -> Gtk.Widget:
        """Builds the Utilities form tab view."""
        self.utility_groups_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)

        header_group = Adw.PreferencesGroup(
            title=_("Utilities Configuration"),
            description=_("Define potential utilities that could be useful to have installed for this game.\n"
                          "These can be mod frameworks or tools that will be helpful for users."),
        )
        main_box.append(header_group)

        main_box.append(self.utility_groups_container)

        # Add Utility Button
        add_btn = Gtk.Button(label=_("Add Utility"))
        add_btn.add_css_class("pill")
        add_btn.set_halign(Gtk.Align.CENTER)
        add_btn.set_cursor_from_name("pointer")
        add_btn.connect("clicked", lambda _: self._add_utility_group())
        main_box.append(add_btn)

        scrolled.set_child(main_box)
        return scrolled

    def _add_utility_group(self, data: dict | None = None) -> None:
        """Creates and appends a single utility group to the container."""
        data = data or {}

        group = Adw.PreferencesGroup()

        name_row = Adw.EntryRow(title=_("Name *"))
        name_row.set_text(data.get("name", ""))
        group.add(name_row)

        version_row = Adw.EntryRow(title=_("Version *"))
        version_row.set_text(data.get("version", ""))
        group.add(version_row)

        creator_row = Adw.EntryRow(title=_("Creator *"))
        creator_row.set_text(data.get("creator", ""))
        group.add(creator_row)

        creator_link_row = Adw.EntryRow(title=_("Creator Link (URL) *"))
        creator_link_row.set_text(data.get("creator-link", ""))
        group.add(creator_link_row)

        source_row = Adw.EntryRow(title=_("Source (URL) *"))
        source_row.set_text(data.get("source", ""))
        group.add(source_row)

        utility_path_row = Adw.EntryRow(title=_("Utility Path *"))
        utility_path_row.set_text(data.get("utility_path", ""))
        group.add(utility_path_row)

        enable_cmd_row = Adw.EntryRow(title=_("Enable Command (Optional)"))
        enable_cmd_row.set_text(data.get("enable_command", ""))
        group.add(enable_cmd_row)

        launch_opts_row = Adw.EntryRow(title=_("Launch Options (Optional)"))
        launch_opts_row.set_text(data.get("launch_options", ""))
        group.add(launch_opts_row)

        delete_btn = Gtk.Button(
            icon_name="mat-delete-symbolic",
            css_classes=["flat", "destructive-action"],
        )
        delete_btn.set_tooltip_text(_("Remove Utility"))
        delete_btn.set_cursor_from_name("pointer")
        delete_btn.connect("clicked", lambda _: self.utility_groups_container.remove(group))
        group.set_header_suffix(delete_btn)

        group.widgets = {
            "name": name_row,
            "version": version_row,
            "creator": creator_row,
            "creator-link": creator_link_row,
            "source": source_row,
            "utility_path": utility_path_row,
            "enable_command": enable_cmd_row,
            "launch_options": launch_opts_row,
        }

        self.utility_groups_container.append(group)

    def _on_save_clicked(self, button):
        has_error = False

        name_val = self.name_row.get_text().strip()
        if not name_val:  # game name is compulsory
            self.name_row.add_css_class("error")
            has_error = True
        else:
            self.name_row.remove_css_class("error")

        modding_paths = []
        child = self.modding_groups_container.get_first_child()

        while child:
            if hasattr(child, "widgets"):
                w = child.widgets
                name = w["name_row"].get_text().strip()
                desc = w["desc_row"].get_text().strip()
                path_segment = w["path_entry"].get_text().strip()

                for widget, val in [
                    (w["name_row"], name),
                    (w["desc_row"], desc),
                ]:
                    if not val:
                        widget.add_css_class("error")
                        has_error = True
                    else:
                        widget.remove_css_class("error")

                if not path_segment:
                    w["path_entry"].add_css_class("error")
                    has_error = True
                else:
                    w["path_entry"].remove_css_class("error")

                base_prefix = (
                    "{user_data}"
                    if w["base_combo"].get_selected() == 1
                    else "{game_path}"
                )

                # Format slashes cleanly
                if not path_segment.startswith("/"):
                    path_segment = f"/{path_segment}"

                full_path = f"{base_prefix}{path_segment}"

                modding_paths.append(
                    {"name": name, "description": desc, "path": full_path}
                )

            child = child.get_next_sibling()

        utilities_data = {}
        invalid_utility_tab = False
        util_child = self.utility_groups_container.get_first_child()

        while util_child:
            if hasattr(util_child, "widgets"):
                w = util_child.widgets

                # Required fields check
                required_fields = [
                    "name", "version", "creator",
                    "creator-link", "source", "utility_path"
                ]

                group_valid = True
                entry_values = {}

                for key, widget in w.items():
                    val = widget.get_text().strip()

                    if key in required_fields:
                        if not val:
                            widget.add_css_class("error")
                            group_valid = False
                            invalid_utility_tab = True
                        else:
                            widget.remove_css_class("error")

                    if key == "name":
                        utility_id = "".join("_" if c == " " else c for c in val if c.isalnum() or c == " ").lower().strip("_")
                    else:
                        entry_values[key] = val

                if group_valid:
                    utilities_data[utility_id] = entry_values
                else:
                    has_error = True

            util_child = util_child.get_next_sibling()

        # If validation fails, stay on or jump to invalid tab
        if has_error:
            if not name_val:
                self.game_info_btn.set_active(True)
            elif invalid_utility_tab:
                self.utilities_btn.set_active(True)
            else:
                self.modding_info_btn.set_active(True)
            return

        rgba = self.color_button.get_rgba()
        hex_color = f"#{int(rgba.red * 255):02x}{int(rgba.green * 255):02x}{int(rgba.blue * 255):02x}"

        config_data = {
            "name": name_val,
            "steam_id": self.steam_id_row.get_text().strip(),
            "steam_folder_name": self.steam_folder_row.get_text().strip(),
            "gog_id": self.gog_id_row.get_text().strip(),
            "nexus_id": self.nexus_id_row.get_text().strip(),
            "accent_colour": hex_color,
            "wiki_link": self.wiki_link_row.get_text().strip(),
            "mods_path": modding_paths,
            "essential_utilities": utilities_data
        }
        custom_configuration_path = os.path.join(CUSTOM_GAME_CONFIG_PATH, name_val.replace(" ", "_").lower()+".yaml")
        write_yaml(config_data, custom_configuration_path)
        print(f"New custom configuration for game {name_val} saved to {custom_configuration_path}")
        self.app.show_loading_and_scan()
        self.close()
        if len(os.listdir(CUSTOM_GAME_CONFIG_PATH)) == 1:
            message_to_user: str = _("Congrats on creating your first game configuration!\n"
                                     "Once you've tested it and made sure it works, please don't hesitate to share it with the NOMM "
                                     "community on our Game Configuration Github repo!\n\n"
                                     "We sincerely hope you continue to enjoy using NOMM :)")
            desc_win = TextWindow(self.app.win, "First configuration created!", message_to_user, text_type="markup")
            desc_win.present()
