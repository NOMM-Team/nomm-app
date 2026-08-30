import gettext
import os
import gi
from typing import Callable
from nomm.core.tools import list_archives
from nomm.core.user_config import load_user_config, LibrarySort

gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GdkPixbuf, Gtk  # noqa: E402

_ = gettext.gettext


class LibraryView(Gtk.Box):
    def __init__(self, app, matches):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.matches = matches

        self.append(Adw.HeaderBar())

        overlay = Gtk.Overlay()
        scroll = Gtk.ScrolledWindow(vexpand=True)

        self.flow = Gtk.FlowBox(
            valign=Gtk.Align.START, halign=Gtk.Align.START,
            selection_mode=Gtk.SelectionMode.NONE,
            margin_top=40, margin_bottom=40, margin_start=40, margin_end=40,
            column_spacing=30, row_spacing=30, homogeneous=True
        )

        if self.matches:
            user_config = load_user_config()
            base_dl_path = user_config.get("download_path")

            for game in self.matches:
                game['mod_count'] = self.calculate_mod_count(game['name'], base_dl_path)

            for game in self.matches:
                self.flow.append(self.create_game_card(game))

            scroll.set_child(self.flow)
            overlay.set_child(scroll)

            sort_mode_str = user_config.get("library_sort", "Number of Mods")
            sort_mode = LibrarySort.from_string(sort_mode_str)
            self.apply_sort(sort_mode)
        else:
            status_page = Adw.StatusPage(
                title=_("No games detected"),
                description=_("We couldn't find any games. This could be due to\n \
                               - You not having any supported games installed\n \
                               - Your Steam/Heroic installation type not being handled\n\n\
                               Feel free to contact me on Discord or Github for more help!"),
                icon_name="input-gaming-symbolic"
            )
            overlay.set_child(status_page)

        self.add_fab_buttons(overlay)
        self.append(overlay)

    def calculate_mod_count(self, game_name, base_dl_path):
        """Calculates archive count for a game."""
        game_dl_path = os.path.join(base_dl_path, game_name)
        if os.path.exists(game_dl_path):
            try:
                return len(list_archives(game_dl_path))
            except Exception as e:
                print(f"Error listing archives for {game_name}: {e}")
        return 0

    def apply_sort(self, sort_mode: LibrarySort = LibrarySort.NUMBER_OF_MODS):
        def sort_func(child1, child2):
            game1 = child1.get_child()._game_data
            game2 = child2.get_child()._game_data

            if sort_mode == LibrarySort.NUMBER_OF_MODS:
                diff = game2.get('mod_count') - game1.get('mod_count')
                if diff != 0:
                    return diff
                return 1 if game1['name'].lower() > game2['name'].lower() else -1
            else:
                name1 = game1['name'].lower()
                name2 = game2['name'].lower()
                if name1 < name2:
                    return -1
                elif name1 > name2:
                    return 1
                return 0

        self.flow.set_sort_func(sort_func)

    def create_game_card(self, game):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card._game_data = game

        card.set_size_request(200, 300)
        card.set_halign(Gtk.Align.START)
        card.set_hexpand(False)
        card.add_css_class("game-card")
        card.set_overflow(Gtk.Overflow.HIDDEN)
        card.set_tooltip_text(f"{game['name']}\n{game['path']}")
        card.set_cursor_from_name("pointer")

        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda g, n, x, y: self.app.on_game_clicked(game))
        card.add_controller(gesture)

        poster = self.get_placeholder_game_poster()

        img_overlay = Gtk.Overlay()
        img_data = game.get('img')
        poster_path = img_data.get('poster') if isinstance(img_data, dict) else None

        if poster_path and os.path.exists(poster_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(poster_path, 200, 300, False)
                poster = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
                poster.set_can_shrink(True)
            except Exception:
                pass

        img_overlay.set_child(poster)

        # Platform badge
        platform = game.get('platform')
        if platform == "steam":
            platform_badge = Gtk.Image.new_from_icon_name("steam-logo")
        elif platform == "heroic-epic":
            platform_badge = Gtk.Image.new_from_icon_name("epic-logo-symbolic")
        elif platform == "heroic-gog":
            platform_badge = Gtk.Image.new_from_icon_name("gog-logo-symbolic")
        elif platform == "switch":
            platform_badge = Gtk.Image.new_from_icon_name("switch-logo-symbolic")
        else:
            print(f"Unrecognised platform: {platform}")
            return
        platform_badge.set_pixel_size(32)
        platform_badge.set_halign(Gtk.Align.END)
        platform_badge.set_valign(Gtk.Align.END)
        platform_badge.set_margin_end(10)
        platform_badge.set_margin_bottom(10)
        platform_badge.add_css_class("platform-badge")

        img_overlay.add_overlay(platform_badge)

        # Mod total badge
        mod_total_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mod_total_badge.set_halign(Gtk.Align.START)
        mod_total_badge.set_valign(Gtk.Align.END)
        mod_total_badge.set_margin_start(10)
        mod_total_badge.set_margin_bottom(10)
        mod_total_badge.add_css_class("platform-badge")

        count = game.get('mod_count', 0)

        mod_total_badge_label = Gtk.Label(label=str(count))
        mod_total_badge_label.add_css_class("badge-accent")
        mod_total_badge.append(mod_total_badge_label)

        img_overlay.add_overlay(mod_total_badge)

        card.append(img_overlay)
        return card

    def add_fab_buttons(self, overlay):
        fab_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=20,
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            margin_top=30,
            margin_end=30,
        )

        def create_library_fab_button(
            *,
            icon_name: str,
            tooltip: str,
            on_click: Callable,
        ) -> Gtk.Button:

            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(42)

            button = Gtk.Button(child=icon)
            button.add_css_class("refresh-fab")
            button.set_size_request(74, 74)
            button.set_tooltip_text(tooltip)
            button.set_cursor_from_name("pointer")

            if on_click:
                button.connect("clicked", on_click)

            return button

        build_config_btn = create_library_fab_button(
            icon_name="add-configuration-symbolic",
            tooltip=_("Create a custom configuration"),
            on_click=self.app.manual_library_refresh
        )

        refresh_btn = create_library_fab_button(
            icon_name="radar-symbolic",
            tooltip=_("Update configurations and re-scan game libraries"),
            on_click=self.app.manual_library_refresh
        )

        settings_btn = create_library_fab_button(
            icon_name="mat-settings-symbolic",
            tooltip=_("Open the settings menu"),
            on_click=self.app.on_settings_clicked
        )

        fab_box.append(build_config_btn)
        fab_box.append(refresh_btn)
        fab_box.append(settings_btn)
        overlay.add_overlay(fab_box)

    def get_placeholder_game_poster(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        img = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
        img.set_pixel_size(128)
        b.append(img)
        return b
