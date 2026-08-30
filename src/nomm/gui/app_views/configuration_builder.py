import gi
import gettext

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib  # noqa: E402
from nomm.platforms.steam import get_installed_steam_games
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
                          "You can either start from scratch or, if the game is already installed, with some fields pre-filled."),
            icon_name="add-configuration-symbolic"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, halign=Gtk.Align.CENTER)
        content_box.set_margin_top(12)
        cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16, halign=Gtk.Align.CENTER)

        selected_starter = {"name": "Custom"}  # Store currently highlighted choice

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
                "text": "Start building from a GOG game that is already installed on your system.\n"
                        "Some configuration fields will be pre-filled for your convenience."
            },
            {
                "name": "Epic",
                "icon": "epic-logo",
                "text": "Start building from an Epic game that is already installed on your system.\n"
                        "Some configuration fields will be pre-filled for your convenience."
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
            label=options[0]["text"],
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
                btn.set_active(True)
            else:
                btn.set_group(group_button)

            # Update selection state when clicked
            def on_toggled(button, name=starter["name"], text=starter["text"], icon=starter["icon"]):
                if button.get_active():
                    selected_starter["name"] = name
                    selected_starter["icon"] = icon
                    desc_label.set_text(text)

            btn.connect("toggled", on_toggled)
            cards_box.append(btn)

        content_box.append(cards_box)

        cont_btn = Gtk.Button(label=_("Continue"), halign=Gtk.Align.CENTER, width_request=160)
        cont_btn.add_css_class("suggested-action")

        def on_continue_clicked(btn):
            if selected_starter["name"] != "Custom":
                self.starter_game_picker(selected_starter)

        cont_btn.connect("clicked", on_continue_clicked)
        content_box.append(desc_label)
        content_box.append(cont_btn)

        status_page.set_child(content_box)

        self.stack.add_named(status_page, "app_builder_starter")
        self.stack.set_visible_child_name("app_builder_starter")

    def starter_game_picker(self, platform):
        self.remove_stack_child("starter_game_picker")
        if platform["name"] == "Steam":
            installed_games = get_installed_steam_games(self.app.game_libraries)
            game_names = [game['name'] for game in installed_games]
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

        # Dropdown with search/type-to-filter support
        string_list = Gtk.StringList.new(game_names)
        dropdown = Gtk.DropDown.new(string_list, None)
        dropdown.set_enable_search(True)
        content_box.append(dropdown)

        cont_btn = Gtk.Button(label=_("Continue"), halign=Gtk.Align.CENTER, width_request=160)
        cont_btn.add_css_class("suggested-action")

        def on_continue_clicked(btn):
            selected_idx = dropdown.get_selected()
            if (
                selected_idx != Gtk.INVALID_LIST_POSITION
                and selected_idx < len(installed_games)
            ):
                selected_game = installed_games[selected_idx]
                # Send the game dict & platform context to your next builder method
                self.on_game_selected(selected_game, platform)

        cont_btn.connect("clicked", on_continue_clicked)
        content_box.append(cont_btn)
        status_page.set_child(content_box)
        self.stack.add_named(status_page, "starter_game_picker")
        self.stack.set_visible_child_name("starter_game_picker")

class ConfigurationBuilderWindow(Adw.MessageDialog):
    pass
