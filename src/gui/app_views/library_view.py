# src/gui/views/library_view.py

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
import gettext
from gi.repository import Gtk, Adw, GdkPixbuf, Gdk

from core.config import load_user_config

_ = gettext.gettext

class LibraryView(Gtk.Box):
    def __init__(self, app, matches):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.matches = matches

        self.append(Adw.HeaderBar())
        
        overlay = Gtk.Overlay()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        
        flow = Gtk.FlowBox(
            valign=Gtk.Align.START, halign=Gtk.Align.START,
            selection_mode=Gtk.SelectionMode.NONE,
            margin_top=40, margin_bottom=40, margin_start=40, margin_end=40,
            column_spacing=30, row_spacing=30, homogeneous=True
        )

        if self.matches:
            for game in self.matches:
                flow.append(self.create_game_card(game))
            scroll.set_child(flow)
            overlay.set_child(scroll)
        else:
            status_page = Adw.StatusPage(
                title=_("No games detected"),
                description=_("We couldn't find any Steam or Heroic games. This could be due to\n - You not having any supported games installed\n - Your Steam/Heroic installation type not being handled\n\n Feel free to contact me on Discord or Github for more help!"),
                icon_name="input-gaming-symbolic"
            )
            overlay.set_child(status_page)

        self.add_fab_buttons(overlay)
        self.append(overlay)

    def create_game_card(self, game):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.set_size_request(200, 300)
        card.set_halign(Gtk.Align.START)
        card.set_hexpand(False)
        card.add_css_class("game-card")
        card.set_overflow(Gtk.Overflow.HIDDEN) 
        card.set_tooltip_text(f"{game['name']}\n{game['path']}")
        
        # Le clic sur la carte renvoie vers la méthode de l'application principale
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda g, n, x, y: self.app.on_game_clicked(game))
        card.add_controller(gesture)

        img_overlay = Gtk.Overlay()
        poster = self.get_placeholder_game_poster()
        
        if game.get('img') and os.path.exists(game['img']):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(game['img'], 200, 300, False)
                poster = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
                poster.set_can_shrink(True)
            except: pass
            
        img_overlay.set_child(poster)
        
        # --- 1. BADGE PLATEFORME ---
        platform = game.get('platform')
        icon_path = ""
        if platform == "steam":
            icon_path = os.path.join(self.app.assets_path, "steam_logo.svg")
        elif platform == "heroic-epic":
            icon_path = os.path.join(self.app.assets_path, "epic_logo.svg")
        elif platform == "heroic-gog":
            icon_path = os.path.join(self.app.assets_path, "gog_logo.svg")

        if os.path.exists(icon_path):
            try:
                platform_badge_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 32, 32, True)
                platform_badge = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(platform_badge_pb))
                
                platform_badge.set_halign(Gtk.Align.END)
                platform_badge.set_valign(Gtk.Align.END)
                platform_badge.set_margin_end(10)
                platform_badge.set_margin_bottom(10)
                platform_badge.add_css_class("platform-badge")
                
                img_overlay.add_overlay(platform_badge)
            except Exception as e:
                print(f"Error rendering SVG badge: {e}")

        # --- 2. BADGE COMPTEUR DE MODS ---
        mod_total_badge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        mod_total_badge.set_halign(Gtk.Align.START)
        mod_total_badge.set_valign(Gtk.Align.END)
        mod_total_badge.set_margin_start(10)
        mod_total_badge.set_margin_bottom(10)
        mod_total_badge.add_css_class("platform-badge")
            
        count = 0
        try:
            user_config = load_user_config()
            base_dl_path = user_config.get("download_path")
            if base_dl_path:
                game_dl_path = os.path.join(base_dl_path, game["name"])
                if os.path.exists(game_dl_path):
                    exts = (".zip", ".rar", ".7z")
                    count = sum(1 for f in os.scandir(game_dl_path) if f.is_file() and f.name.lower().endswith(exts))
        except: pass
        
        mod_total_badge_label = Gtk.Label(label=str(count))
        mod_total_badge_label.add_css_class("badge-accent")
        mod_total_badge.append(mod_total_badge_label)
        
        img_overlay.add_overlay(mod_total_badge)

        card.append(img_overlay)
        return card

    def add_fab_buttons(self, overlay):
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", halign=Gtk.Align.END, valign=Gtk.Align.START, margin_top=30, margin_end=30)
        refresh_btn.set_size_request(64, 64)
        refresh_btn.add_css_class("refresh-fab")
        # Appelle la méthode de rafraîchissement de l'app principale
        refresh_btn.connect("clicked", lambda b: self.app.show_loading_and_scan())

        settings_btn = Gtk.Button(icon_name="settings-configure-symbolic", halign=Gtk.Align.END, valign=Gtk.Align.START, margin_top=30, margin_end=120)
        settings_btn.set_size_request(64, 64)
        settings_btn.add_css_class("refresh-fab")
        settings_btn.connect("clicked", self.app.on_settings_clicked)
        
        overlay.add_overlay(settings_btn)
        overlay.add_overlay(refresh_btn)

    def get_placeholder_game_poster(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        img = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
        img.set_pixel_size(128)
        b.append(img)
        return b