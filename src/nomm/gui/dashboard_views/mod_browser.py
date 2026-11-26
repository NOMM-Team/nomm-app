import gettext
import cairo
import time
import datetime
import threading
import os
import hashlib
import urllib.request
from gi.repository import Gtk, Adw, Gio, GObject, Gdk, GLib
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from nomm.gui.ui_builders import create_icon_button
from nomm.core.tools import format_count, format_relative_date, parse_iso_timestamp
from nomm.core.user_config import load_user_config, update_user_config, CACHE_DIR
from nomm.core.mod_manager import load_downloaded_mod_ids
from nomm.platforms.nexus import search_nexus_mods, get_nexus_first_mod_date
from nomm.platforms.gamebanana import (search_gamebanana_mods, get_gamebanana_first_mod_date, _build_gamebanana_protocol_url)
_ = gettext.gettext


class ModItem(GObject.Object):
    __gtype_name__ = 'ModItem'

    name = GObject.Property(type=str, default="")
    author = GObject.Property(type=str, default="")
    thumbnail_url = GObject.Property(type=str, default="")
    short_description = GObject.Property(type=str, default="")
    page_url = GObject.Property(type=str, default="")
    download_url = GObject.Property(type=str, default="")
    downloads_or_views = GObject.Property(type=int, default=0)
    endorsements = GObject.Property(type=int, default=0)
    mod_id = GObject.Property(type=str, default="")
    created_at = GObject.Property(type=float, default=0.0)
    updated_at = GObject.Property(type=float, default=0.0)

    def __init__(
        self,
        name="",
        uploader="",
        thumbnail_url="",
        downloads_or_views=0,
        endorsements=0,
        short_description="",
        page_url="",
        download_url="",
        mod_id="",
        created_at=0.0,
        updated_at=0.0
    ):
        super().__init__()
        self.props.name = name
        self.props.author = uploader
        self.props.thumbnail_url = thumbnail_url
        self.props.downloads_or_views = downloads_or_views
        self.props.endorsements = endorsements
        self.props.short_description = short_description
        self.props.page_url = page_url
        self.props.download_url = download_url
        self.props.mod_id = str(mod_id or "")
        self.props.created_at = parse_iso_timestamp(created_at)
        self.props.updated_at = parse_iso_timestamp(updated_at)


class BaseModProvider:
    """Agnostic interface for mod websites (GameBanana, Nexus, Thunderstore)."""
    def search_mods(self, query: str, category: str, sort_by: str, date_range: tuple, updated_range: tuple, include_adult: bool,
                    author: str = "", count: int = 20, offset: int = 0) -> list[ModItem]:
        raise NotImplementedError

    def get_browse_mods(self) -> list[ModItem]:
        raise NotImplementedError

    def get_first_mod_date(self) -> float:
        raise NotImplementedError


class NexusModProvider(BaseModProvider):
    def __init__(self, game_info: dict | None = None, headers: dict | None = None):
        self.game_info = game_info or {}
        self.headers = dict(headers) if headers else {}

    def get_first_mod_date(self) -> float:
        game_domain = str(
            self.game_info.get("nexus_domain")
            or self.game_info.get("nexus_id")
            or ""
        )
        return get_nexus_first_mod_date(
            headers=self.headers,
            game_domain=game_domain
        )

    def search_mods(self, query: str, category: str, sort_by: str, date_range: tuple, updated_range: tuple, include_adult: bool,
                    author: str = "", count: int = 20, offset: int = 0) -> list[ModItem]:
        game_domain = self.game_info.get("nexus_id", "")
        if not game_domain:
            return []

        raw_results = search_nexus_mods(
            headers=self.headers,
            game_domain=game_domain,
            query=query,
            category=category,
            sort_by=sort_by,
            date_range=date_range,
            updated_range=updated_range,
            include_adult=include_adult,
            author=author,
            count=count,
            offset=offset
        )

        return [
            ModItem(
                name=item["name"],
                uploader=item["author"],
                thumbnail_url=item["thumbnail_url"],
                downloads_or_views=item["downloads"],
                endorsements=item["endorsements"],
                short_description=item["short_description"],
                page_url=item["page_url"],
                download_url=item["download_url"],
                mod_id=str(item["mod_id"]),
                created_at=item.get("created_at") or item.get("created_timestamp") or 0.0,
                updated_at=item.get("updated_at") or item.get("updated_timestamp") or 0.0
            )
            for item in raw_results
        ]

    def get_browse_mods(self) -> list[ModItem]:
        first_mod_date = self.get_first_mod_date()
        return self.search_mods(
            query="",
            category="All Categories",
            sort_by="Most Downloaded first",
            date_range=(first_mod_date, time.time()),
            updated_range=(first_mod_date, time.time()),
            include_adult=False,
        )


class GameBananaModProvider(BaseModProvider):
    def __init__(self, game_info: dict | None = None, headers: dict | None = None):
        self.game_info = game_info or {}
        self.headers = dict(headers) if headers else {}

    def get_first_mod_date(self) -> float:
        game_id = self.game_info.get("gamebanana_id") or ""
        return get_gamebanana_first_mod_date(headers=self.headers, game_id=game_id)

    def get_protocol_download_url(self, mod_item: ModItem) -> str:
        if not mod_item:
            return ""
        return _build_gamebanana_protocol_url(
            mod_item.props.mod_id,
            download_url=mod_item.props.download_url,
            headers=self.headers,
        )

    def search_mods(
        self,
        query: str,
        category: str,
        sort_by: str,
        date_range: tuple,
        updated_range: tuple,
        include_adult: bool,
        author: str = "",
        count: int = 20,
        offset: int = 0,
    ) -> list[ModItem]:
        game_id = self.game_info.get("gamebanana_id", "")
        if not game_id:
            return []

        raw_results = search_gamebanana_mods(
            headers=self.headers,
            game_id=game_id,
            query=query,
            category=category,
            sort_by=sort_by,
            date_range=date_range,
            updated_range=updated_range,
            include_adult=include_adult,
            author=author,
            count=count,
            offset=offset,
        )

        return [
            ModItem(
                name=item["name"],
                uploader=item["author"],
                thumbnail_url=item["thumbnail_url"],
                downloads_or_views=item["views"],
                endorsements=item["endorsements"],
                short_description=item["short_description"],
                page_url=item["page_url"],
                download_url=item["download_url"],
                mod_id=str(item["mod_id"]),
                created_at=item.get("created_at", 0.0),
                updated_at=item.get("updated_at", 0.0),
            )
            for item in raw_results
        ]

    def get_browse_mods(self) -> list[ModItem]:
        first_mod_date = self.get_first_mod_date()
        return self.search_mods(
            query="",
            category="All Categories",
            sort_by="Most Downloaded first",
            date_range=(first_mod_date, time.time()),
            updated_range=(first_mod_date, time.time()),
            include_adult=False,
        )


class StoreProvider(BaseModProvider):
    def __init__(self, store_name: str, game_info: dict | None = None, headers: dict | None = None):
        self.store_name = store_name
        self.headers = dict(headers) if headers else {}
        self.game_info = game_info or {}

    def _slug(self) -> str:
        return self.store_name.lower().replace(" ", "-")

    def search_mods(
        self,
        query: str,
        category: str,
        sort_by: str,
        date_range: tuple,
        updated_range: tuple = (),
        include_adult: bool = False,
        author: str = "",
        count: int = 20,
        offset: int = 0,
    ) -> list[ModItem]:

        print(
            f"Searching {self.store_name}: query='{query}', category='{category}', "
            f"sort='{sort_by}', date_range='{date_range}', adult={include_adult}"
        )
        slug = self._slug()
        return [
            ModItem(
                name=f"{self.store_name} Result: {query or 'All'} #{i}",
                uploader=f"Author {i}",
                downloads_or_views=i * 14500,
                endorsements=i * 620,
                page_url=f"https://example.org/{slug}/mods/{i}",
                download_url=f"https://example.org/{slug}/mods/{i}/download.zip",
            )
            for i in range(1, 13)
        ]

    def get_browse_mods(self) -> list[ModItem]:
        slug = self._slug()
        return [
            ModItem(
                name=f"{self.store_name} Trending Mod #{i}",
                uploader=f"Author {i}",
                thumbnail_url="",
                page_url=f"https://example.org/{slug}/mods/{i}",
                download_url=f"https://example.org/{slug}/mods/{i}/download.zip",
            )
            for i in range(1, 25)
        ]

    def get_first_mod_date(self) -> float:
        return 1420070400  # Jan 1, 2015


class DualRangeSlider(Gtk.Box):
    """A custom GTK4 slider widget featuring two points (low and high thumbs)."""
    __gsignals__ = {
        "range-changed": (GObject.SignalFlags.RUN_FIRST, None, (float, float))
    }

    def __init__(self, min_val: float, max_val: float):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.min_val = min_val
        self.max_val = max_val
        self.low_val = min_val
        self.high_val = max_val

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_size_request(220, 36)
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_draw_func(self.on_draw)

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.drawing_area.add_controller(drag)

        self.append(self.drawing_area)

        self.label = Gtk.Label(label=self._get_range_text())
        self.label.add_css_class("dim-label")
        self.label.set_halign(Gtk.Align.CENTER)
        self.append(self.label)

        self.active_thumb = None
        self.start_low = min_val
        self.start_high = max_val

    def set_range_values(self, low: float, high: float):
        """Programmatically sync slider values without firing recursive signals."""
        self.low_val = max(self.min_val, min(low, self.max_val))
        self.high_val = max(self.low_val, min(high, self.max_val))
        self.label.set_text(self._get_range_text())
        self.drawing_area.queue_draw()

    def _get_range_text(self) -> str:
        try:
            if abs(self.low_val - self.min_val) < 1.0:
                d_low = _("Game release")
            else:
                dt_low = datetime.datetime.fromtimestamp(self.low_val)
                d_low = f"{dt_low.day} {dt_low.strftime('%b').lower()} {dt_low.strftime('%Y')}"

            if abs(self.high_val - self.max_val) < 1.0:
                d_high = _("now")
            else:
                dt_high = datetime.datetime.fromtimestamp(self.high_val)
                d_high = f"{dt_high.day} {dt_high.strftime('%b').lower()} {dt_high.strftime('%Y')}"

            return _("{start} to {end}").format(start=d_low, end=d_high)
        except Exception:
            low_str = _("Game release") if abs(self.low_val - self.min_val) < 1.0 else str(int(self.low_val))
            high_str = _("now") if abs(self.high_val - self.max_val) < 1.0 else str(int(self.high_val))
            return f"{low_str} - {high_str}"

    def on_draw(self, area, cr, width, height):
        padding = 16
        usable_width = width - (2 * padding)
        if usable_width <= 0:
            return

        def val_to_x(val):
            if self.max_val == self.min_val:
                return padding
            return padding + (val - self.min_val) / (self.max_val - self.min_val) * usable_width

        low_x = val_to_x(self.low_val)
        high_x = val_to_x(self.high_val)
        y = height / 2

        cr.set_source_rgba(0.5, 0.5, 0.5, 0.25)
        cr.set_line_width(6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(padding, y)
        cr.line_to(width - padding, y)
        cr.stroke()

        cr.set_source_rgb(0.21, 0.52, 0.89)
        cr.set_line_width(6)
        cr.move_to(low_x, y)
        cr.line_to(high_x, y)
        cr.stroke()

        radius = 7
        for thumb_x in [low_x, high_x]:
            cr.set_source_rgb(1, 1, 1)
            cr.arc(thumb_x, y, radius, 0, 2 * 3.1415926535)
            cr.fill_preserve()

            cr.set_source_rgb(0.21, 0.52, 0.89)
            cr.set_line_width(2)
            cr.stroke()

    def on_drag_begin(self, gesture, start_x, start_y):
        width = self.drawing_area.get_width()
        padding = 16
        usable_width = width - (2 * padding)
        if usable_width <= 0:
            return

        def val_to_x(val):
            if self.max_val == self.min_val:
                return padding
            return padding + (val - self.min_val) / (self.max_val - self.min_val) * usable_width

        low_x = val_to_x(self.low_val)
        high_x = val_to_x(self.high_val)

        if abs(start_x - low_x) < abs(start_x - high_x):
            self.active_thumb = 'low'
        else:
            self.active_thumb = 'high'

        self.start_low = self.low_val
        self.start_high = self.high_val

    def on_drag_update(self, gesture, offset_x, offset_y):
        width = self.drawing_area.get_width()
        padding = 16
        usable_width = width - (2 * padding)
        if usable_width <= 0:
            return

        delta_val = (offset_x / usable_width) * (self.max_val - self.min_val)

        if self.active_thumb == 'low':
            new_val = self.start_low + delta_val
            self.low_val = max(self.min_val, min(new_val, self.high_val))
        elif self.active_thumb == 'high':
            new_val = self.start_high + delta_val
            self.high_val = max(self.low_val, min(new_val, self.max_val))

        self.label.set_text(self._get_range_text())
        self.drawing_area.queue_draw()
        self.emit("range-changed", self.low_val, self.high_val)

    def on_drag_end(self, gesture, offset_x, offset_y):
        self.active_thumb = None


class ThumbnailLoader:
    """Fetches images off the main thread with a RAM Gdk.Texture cache and disk cache."""

    def __init__(
        self,
        max_memory_items: int = 256,
        max_workers: int = 6,
        cache_dir: str | os.PathLike | None = None,
    ):
        self._max_memory_items = max_memory_items
        self._cache: OrderedDict[str, Gdk.Texture] = OrderedDict()
        self._in_flight: set[str] = set()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="thumb-loader")

        base_cache = os.fspath(cache_dir) if cache_dir is not None else os.fspath(CACHE_DIR)
        self._cache_dir = os.path.join(base_cache, "browser_thumbnails")
        os.makedirs(self._cache_dir, exist_ok=True)

    def _disk_path_for_url(self, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return os.path.join(self._cache_dir, digest)

    def _read_disk_bytes(self, disk_path: str) -> bytes | None:
        if not os.path.isfile(disk_path):
            return None
        try:
            with open(disk_path, "rb") as f:
                data = f.read()
            return data if data else None
        except Exception:
            return None

    def _write_disk_bytes(self, disk_path: str, data: bytes):
        tmp_path = f"{disk_path}.{threading.get_ident()}.tmp"
        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.replace(tmp_path, disk_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _decode_texture(self, data: bytes) -> Gdk.Texture | None:
        if not data:
            return None
        try:
            glib_bytes = GLib.Bytes.new(data)
            return Gdk.Texture.new_from_bytes(glib_bytes)
        except Exception:
            return None

    def get_cached(self, url: str) -> Gdk.Texture | None:
        if not url:
            return None
        with self._lock:
            tex = self._cache.get(url)
            if tex is not None:
                self._cache.move_to_end(url)
            return tex

    def _put_cache(self, url: str, texture: Gdk.Texture):
        with self._lock:
            self._cache[url] = texture
            self._cache.move_to_end(url)
            while len(self._cache) > self._max_memory_items:
                self._cache.popitem(last=False)

    def load(self, url: str, on_loaded):
        """Calls `on_loaded(url, texture_or_none)` on the GTK main thread."""
        if not url:
            GLib.idle_add(on_loaded, url, None)
            return

        cached = self.get_cached(url)
        if cached is not None:
            GLib.idle_add(on_loaded, url, cached)
            return

        with self._lock:
            if url in self._in_flight:
                return
            self._in_flight.add(url)

        self._executor.submit(self._worker, url, on_loaded)

    def _worker(self, url: str, on_loaded):
        texture = None
        disk_path = self._disk_path_for_url(url)
        try:
            disk_data = self._read_disk_bytes(disk_path)
            if disk_data is not None:
                texture = self._decode_texture(disk_data)
                if texture is None:
                    try:
                        os.remove(disk_path)
                    except Exception:
                        pass

            if texture is None:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "nomm-mod-browser/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    net_data = resp.read()
                if net_data:
                    texture = self._decode_texture(net_data)
                    if texture is not None:
                        self._write_disk_bytes(disk_path, net_data)

            if texture is not None:
                self._put_cache(url, texture)
        except Exception:
            texture = None
        finally:
            with self._lock:
                self._in_flight.discard(url)
            GLib.idle_add(on_loaded, url, texture)

    def shutdown(self):
        self._executor.shutdown(wait=False)


class StoreView(Gtk.Box):
    def __init__(self, provider: BaseModProvider, game_info: dict | None = None, downloaded_mod_ids: set[str] | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.provider = provider
        self.game_info = game_info or {}
        self.model = Gio.ListStore(item_type=ModItem)
        self._downloaded_mod_ids = downloaded_mod_ids or set()
        self._raw_results: list[ModItem] = []
        self._current_author = ""
        self._syncing = False
        self._page_size = 20
        self._next_offset = 0
        self._loading_more = False
        self._has_more = True
        self._current_search_params: tuple | None = None
        self._thumb_loader = ThumbnailLoader()

        user_cfg = load_user_config() or {}
        self._include_adult_default = bool(user_cfg.get("show_adult_mods_in_browse", False))
        self._hide_downloaded_default = bool(user_cfg.get("hide_downloaded_mods", False))

        self.categories_model = Gtk.StringList.new(["All Categories", "Gameplay", "Visuals", "Audio", "Tools"])
        self.sort_model = Gtk.StringList.new(["Most Downloaded first", "Highest Rated first", "Newest first", "Oldest first"])
        self.min_date = self.provider.get_first_mod_date()
        self.max_date = time.time()

        self.header = Adw.HeaderBar()
        self._build_browse_header_controls()
        self.append(self.header)

        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)

        self._build_search_page()
        self._build_browse_page()

        self.stack.set_visible_child_name("search")
        self.append(self.stack)

    def _create_filter_controls(self) -> dict:
        """Builds a fresh filter group and its associated filter rows/sliders."""
        group = Adw.PreferencesGroup()

        category_row = Adw.ComboRow(title="Category", model=self.categories_model)
        group.add(category_row)

        uploaded_slider = DualRangeSlider(self.min_date, self.max_date)
        uploaded_row = Adw.ActionRow(title=_("Uploaded"))
        uploaded_row.set_subtitle(_("Publication date"))
        uploaded_row.add_suffix(uploaded_slider)
        group.add(uploaded_row)

        updated_slider = DualRangeSlider(self.min_date, self.max_date)
        updated_row = Adw.ActionRow(title=_("Updated"))
        updated_row.set_subtitle(_("Last updated date"))
        updated_row.add_suffix(updated_slider)
        group.add(updated_row)

        adult_row = Adw.SwitchRow(
            title="Include Adult Content",
            subtitle=_("Show mods flagged as NSFW"),
        )
        adult_row.set_active(self._include_adult_default)
        adult_row.connect("notify::active", self._on_adult_row_toggled)
        group.add(adult_row)

        hide_downloaded_row = Adw.SwitchRow(
            title=_("Hide Downloaded Mods"),
            subtitle=_("Hide mods already present download metadata"),
        )
        hide_downloaded_row.set_active(self._hide_downloaded_default)
        hide_downloaded_row.connect("notify::active", self._on_hide_downloaded_toggled)
        group.add(hide_downloaded_row)

        return {
            "group": group,
            "category_row": category_row,
            "uploaded_slider": uploaded_slider,
            "updated_slider": updated_slider,
            "adult_row": adult_row,
            "hide_downloaded_row": hide_downloaded_row,
        }

    def _build_browse_header_controls(self):
        """Creates the compact search bar, filter button, and dedicated sort button for Browse mode."""
        self.header_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.header_controls_box.set_visible(False)

        self.compact_search_entry = Gtk.SearchEntry()
        self.compact_search_entry.set_placeholder_text("Search mods...")
        self.compact_search_entry.set_size_request(280, -1)
        self.compact_search_entry.connect("activate", lambda *_: self.execute_search(from_compact=True))
        self.header_controls_box.append(self.compact_search_entry)

        self.filter_menu_btn = Gtk.MenuButton()
        filter_icon = Gtk.Image.new_from_icon_name("mat-search-settings-symbolic")
        filter_icon.set_pixel_size(24)
        self.filter_menu_btn.set_child(filter_icon)
        self.filter_menu_btn.set_tooltip_text("Filter")
        self.filter_menu_btn.add_css_class("flat")

        filter_popover = Gtk.Popover()
        pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        pop_box.set_margin_top(12)
        pop_box.set_margin_bottom(12)
        pop_box.set_margin_start(12)
        pop_box.set_margin_end(12)
        pop_box.set_size_request(360, -1)

        self.pop_filters = self._create_filter_controls()
        self.pop_category_row = self.pop_filters["category_row"]
        self.pop_uploaded_slider = self.pop_filters["uploaded_slider"]
        self.pop_updated_slider = self.pop_filters["updated_slider"]
        self.pop_adult_row = self.pop_filters["adult_row"]
        self.pop_hide_downloaded_row = self.pop_filters["hide_downloaded_row"]

        pop_box.append(self.pop_filters["group"])

        filter_popover.set_child(pop_box)
        self.filter_menu_btn.set_popover(filter_popover)
        self.header_controls_box.append(self.filter_menu_btn)

        self.sort_menu_btn = Gtk.MenuButton()
        sort_icon = Gtk.Image.new_from_icon_name("mat-sort-symbolic")
        sort_icon.set_pixel_size(24)
        self.sort_menu_btn.set_child(sort_icon)
        self.sort_menu_btn.set_tooltip_text("Sort by")
        self.sort_menu_btn.add_css_class("flat")

        sort_popover = Gtk.Popover()
        sort_list_box = Gtk.ListBox()
        sort_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        sort_list_box.add_css_class("boxed-list")

        self.selected_sort_index = 0
        self._sort_check_icons = []

        for idx in range(self.sort_model.get_n_items()):
            label_text = self.sort_model.get_string(idx)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row_box.set_margin_top(8)
            row_box.set_margin_bottom(8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)

            lbl = Gtk.Label(label=label_text, xalign=0, hexpand=True)
            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.set_opacity(1.0 if idx == 0 else 0.0)
            self._sort_check_icons.append(check)

            row_box.append(lbl)
            row_box.append(check)

            row = Gtk.ListBoxRow()
            row.set_child(row_box)
            row.sort_index = idx
            sort_list_box.append(row)

        def on_sort_row_activated(_, row):
            self._set_browse_sort_index(row.sort_index)
            sort_popover.popdown()
            self.execute_search(from_compact=True)

        sort_list_box.connect("row-activated", on_sort_row_activated)
        sort_popover.set_child(sort_list_box)
        self.sort_menu_btn.set_popover(sort_popover)
        self.header_controls_box.append(self.sort_menu_btn)

        self.header.set_title_widget(self.header_controls_box)

    def _set_browse_sort_index(self, index: int):
        self.selected_sort_index = index
        for idx, check_icon in enumerate(self._sort_check_icons):
            check_icon.set_opacity(1.0 if idx == index else 0.0)

    def _build_search_page(self):
        search_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        search_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        search_page_box.set_valign(Gtk.Align.CENTER)
        search_page_box.set_halign(Gtk.Align.CENTER)
        search_page_box.set_size_request(500, -1)
        search_page_box.set_margin_top(24)
        search_page_box.set_margin_bottom(24)
        search_page_box.set_margin_start(24)
        search_page_box.set_margin_end(24)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search mods...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("activate", lambda *_: self.execute_search(from_compact=False))
        search_box.append(self.search_entry)

        search_btn = Gtk.Button(label="Search Mods")
        search_btn.add_css_class("pill")
        search_btn.add_css_class("suggested-action")
        search_btn.connect("clicked", lambda *_: self.execute_search(from_compact=False))
        search_box.append(search_btn)

        search_page_box.append(search_box)

        self.search_filters = self._create_filter_controls()
        self.category_row = self.search_filters["category_row"]
        self.uploaded_date_slider = self.search_filters["uploaded_slider"]
        self.updated_date_slider = self.search_filters["updated_slider"]
        self.adult_row = self.search_filters["adult_row"]
        self.hide_downloaded_row = self.search_filters["hide_downloaded_row"]

        self.sort_row = Adw.ComboRow(title="Sort by", model=self.sort_model)
        sort_group = Adw.PreferencesGroup()
        sort_group.add(self.sort_row)

        search_page_box.append(self.search_filters["group"])
        search_page_box.append(sort_group)

        search_scroll.set_child(search_page_box)

        self.stack.add_named(search_scroll, "search")

    def _build_browse_page(self):
        browse_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        self.selection_model = Gtk.NoSelection(model=self.model)
        self.grid_view = Gtk.GridView(model=self.selection_model, factory=factory)
        self.grid_view.set_max_columns(6)
        self.grid_view.set_min_columns(2)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self.grid_view)

        vadj = scrolled.get_vadjustment()
        vadj.connect("value-changed", self._on_vadj_value_changed)

        browse_box.append(scrolled)

        self.stack.add_named(browse_box, "browse")

    def execute_search(self, from_compact: bool = False):
        if not from_compact:
            # One-time copy from the initial search page to the browse header
            self.compact_search_entry.set_text(self.search_entry.get_text())
            self.pop_category_row.set_selected(self.category_row.get_selected())
            self._set_browse_sort_index(self.sort_row.get_selected())
            self.pop_adult_row.set_active(self.adult_row.get_active())
            self.pop_hide_downloaded_row.set_active(self.hide_downloaded_row.get_active())
            self.pop_uploaded_slider.set_range_values(self.uploaded_date_slider.low_val, self.uploaded_date_slider.high_val)
            self.pop_updated_slider.set_range_values(self.updated_date_slider.low_val, self.updated_date_slider.high_val)

        query = self.compact_search_entry.get_text().strip()

        category_item = self.pop_category_row.get_selected_item()
        category = category_item.get_string() if category_item else "All Categories"

        sort_by = self.sort_model.get_string(self.selected_sort_index) or "Most Downloaded first"

        date_range = (self.pop_uploaded_slider.low_val, self.pop_uploaded_slider.high_val)
        updated_range = (self.pop_updated_slider.low_val, self.pop_updated_slider.high_val)
        include_adult = self.pop_adult_row.get_active()

        self._current_author = ""
        self._current_search_params = (query, category, sort_by, date_range, updated_range, include_adult)
        self._next_offset = 0
        self._has_more = True

        results = self.provider.search_mods(
            query,
            category,
            sort_by,
            date_range,
            updated_range,
            include_adult,
            count=self._page_size,
            offset=0,
        )

        self._raw_results = list(results)
        visible_mods = self._filter_mods(self._raw_results)

        self.model.remove_all()
        for mod in visible_mods:
            self.model.append(mod)

        self._next_offset = len(results)
        self._has_more = len(results) >= self._page_size

        self.header_controls_box.set_visible(True)
        self.stack.set_visible_child_name("browse")

    def _on_vadj_value_changed(self, adj: Gtk.Adjustment):
        if self.stack.get_visible_child_name() != "browse":
            return
        if self._loading_more or not self._has_more or not self._current_search_params:
            return

        upper = adj.get_upper()
        page_size = adj.get_page_size()
        if upper <= page_size:
            return

        if adj.get_value() + page_size >= upper - 120:
            self.load_more_mods()

    def load_more_mods(self):
        if self._loading_more or not self._has_more or not self._current_search_params:
            return

        self._loading_more = True
        query, category, sort_by, date_range, updated_range, include_adult = self._current_search_params
        author = self._current_author
        count = self._page_size
        offset = self._next_offset

        def _worker():
            try:
                more_results = self.provider.search_mods(
                    query,
                    category,
                    sort_by,
                    date_range,
                    updated_range,
                    include_adult,
                    author=author,
                    count=count,
                    offset=offset,
                )
            except Exception as e:
                print(f"Failed to load more mods: {e}")
                more_results = []

            GLib.idle_add(self._on_more_mods_loaded, more_results)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_more_mods_loaded(self, more_results: list[ModItem]):
        try:
            self._raw_results.extend(more_results)
            visible = self._filter_mods(more_results)
            if visible:
                self.model.splice(self.model.get_n_items(), 0, visible)

            self._next_offset += len(more_results)
            if len(more_results) < self._page_size:
                self._has_more = False
        finally:
            self._loading_more = False
        return False

    def on_factory_setup(self, factory, list_item):
        overlay = Gtk.Overlay()
        overlay.set_size_request(220, 180)
        overlay.set_margin_top(8)
        overlay.set_margin_bottom(8)
        overlay.set_margin_start(8)
        overlay.set_margin_end(8)

        card = Gtk.Overlay()
        card.add_css_class("card")
        card.set_overflow(Gtk.Overflow.HIDDEN)
        card.set_hexpand(True)
        card.set_vexpand(True)
        card.current_mod = None
        card.overlay = overlay
        card._thumb_request_id = 0

        bg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bg_box.set_hexpand(True)
        bg_box.set_vexpand(True)

        picture = Gtk.Picture()
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        bg_box.append(picture)

        fallback_icon = Gtk.Image(icon_name="nomm-logo", pixel_size=64)
        fallback_icon.set_vexpand(True)
        fallback_icon.set_valign(Gtk.Align.CENTER)
        bg_box.append(fallback_icon)

        card.set_child(bg_box)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text_box.set_valign(Gtk.Align.END)
        text_box.set_hexpand(True)
        text_box.add_css_class("mod-text-scrim")

        title_label = Gtk.Label(ellipsize=3)
        title_label.add_css_class("heading")
        title_label.set_halign(Gtk.Align.CENTER)
        text_box.append(title_label)

        author_btn = Gtk.Button()
        author_btn.add_css_class("flat")
        author_btn.set_halign(Gtk.Align.CENTER)

        author_label = Gtk.Label(ellipsize=3)
        author_label.add_css_class("dim-label")
        author_btn.set_child(author_label)

        def on_author_clicked(_btn, c=card):
            if c.current_mod and c.current_mod.props.author:
                self.search_by_author(c.current_mod.props.author)

        author_btn.connect("clicked", on_author_clicked)
        text_box.append(author_btn)

        card.add_overlay(text_box)

        overlay.set_child(card)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        stats_box.add_css_class("mod-stats-scrim")
        stats_box.set_halign(Gtk.Align.START)
        stats_box.set_valign(Gtk.Align.START)

        published_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        published_box.set_halign(Gtk.Align.START)
        published_icon = Gtk.Image.new_from_icon_name("mat-publish-symbolic")
        published_icon.set_pixel_size(13)
        published_label = Gtk.Label(label="—")
        published_label.add_css_class("caption")
        published_box.append(published_icon)
        published_box.append(published_label)

        updated_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        updated_box.set_halign(Gtk.Align.START)
        updated_icon = Gtk.Image.new_from_icon_name("mat-update-symbolic")
        updated_icon.set_pixel_size(13)
        updated_label = Gtk.Label(label="—")
        updated_label.add_css_class("caption")
        updated_box.append(updated_icon)
        updated_box.append(updated_label)

        downloads_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        downloads_box.set_halign(Gtk.Align.START)
        downloads_icon = Gtk.Image.new_from_icon_name("downloaded-symbolic")
        downloads_icon.set_pixel_size(13)
        downloads_label = Gtk.Label(label="0")
        downloads_label.add_css_class("caption")
        downloads_box.append(downloads_icon)
        downloads_box.append(downloads_label)

        endorsements_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        endorsements_box.set_halign(Gtk.Align.START)
        endorsements_icon = Gtk.Image.new_from_icon_name("mat-donate-symbolic")
        endorsements_icon.set_pixel_size(13)
        endorsements_label = Gtk.Label(label="0")
        endorsements_label.add_css_class("caption")
        endorsements_box.append(endorsements_icon)
        endorsements_box.append(endorsements_label)

        stats_box.append(published_box)
        stats_box.append(updated_box)
        stats_box.append(downloads_box)
        stats_box.append(endorsements_box)
        overlay.add_overlay(stats_box)

        # Top-right actions overlay (unchanged)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions_box.set_halign(Gtk.Align.END)
        actions_box.set_valign(Gtk.Align.START)
        actions_box.set_margin_top(8)
        actions_box.set_margin_end(8)

        download_btn = create_icon_button(
            icon_name="refresh-mods-symbolic",
            tooltip="Download mod",
            icon_margin=2,
            css_classes=["circular", "osd"],
            on_click=lambda _, c=card: self._on_download_clicked(c.current_mod),
        )
        actions_box.append(download_btn)

        overlay.add_overlay(actions_box)

        click_gesture = Gtk.GestureClick.new()
        click_gesture.set_button(Gdk.BUTTON_PRIMARY)
        click_gesture.connect("released", lambda *_, c=card: self._on_open_page_clicked(c.current_mod))
        overlay.add_controller(click_gesture)

        card.picture = picture
        card.fallback_icon = fallback_icon
        card.title_label = title_label
        card.author_label = author_label
        card.downloads_box = downloads_box
        card.downloads_icon = downloads_icon
        card.downloads_label = downloads_label
        card.endorsements_box = endorsements_box
        card.endorsements_label = endorsements_label
        card.download_btn = download_btn
        card.published_box = published_box
        card.published_label = published_label
        card.updated_box = updated_box
        card.updated_label = updated_label

        list_item.set_child(overlay)

    def on_factory_bind(self, factory, list_item):
        overlay = list_item.get_child()
        card = overlay.get_child()
        mod_item = list_item.get_item()

        card.current_mod = mod_item
        card.title_label.set_text(mod_item.props.name)
        card.author_label.set_text(mod_item.props.author)
        is_gb = isinstance(self.provider, GameBananaModProvider)
        count_val = mod_item.props.downloads_or_views

        card.downloads_icon.set_from_icon_name(
            "mat-visibility-symbolic" if is_gb else "downloaded-symbolic"
        )
        card.downloads_label.set_text(format_count(count_val))
        stat_unit = _("views") if is_gb else _("downloads")
        card.downloads_box.set_tooltip_text(f"{count_val:,} {stat_unit}")
        card.endorsements_label.set_text(format_count(mod_item.props.endorsements))
        card.endorsements_box.set_tooltip_text(f"{mod_item.props.endorsements:,} endorsements")

        thumb_url = (mod_item.props.thumbnail_url or "").strip()
        card._thumb_request_id = getattr(card, "_thumb_request_id", 0) + 1
        req_id = card._thumb_request_id

        cached_tex = self._thumb_loader.get_cached(thumb_url) if thumb_url else None
        if cached_tex is not None:
            card.picture.set_paintable(cached_tex)
            card.fallback_icon.set_visible(False)
        else:
            card.picture.set_paintable(None)
            card.fallback_icon.set_visible(True)
            if thumb_url:
                self._thumb_loader.load(
                    thumb_url,
                    lambda url, tex, c=card, m=mod_item, u=thumb_url, rid=req_id: self._apply_thumbnail(
                        c, m, u, rid, tex
                    ),
                )

        btn_image = card.download_btn.get_child()
        if str(mod_item.props.mod_id).strip() in self._downloaded_mod_ids:
            if isinstance(btn_image, Gtk.Image):
                btn_image.set_from_icon_name("object-select-symbolic")
            card.download_btn.set_tooltip_text(_("Already downloaded"))
            card.download_btn.set_sensitive(False)
        else:
            if isinstance(btn_image, Gtk.Image):
                btn_image.set_from_icon_name("refresh-mods-symbolic")
            card.download_btn.set_tooltip_text(_("Download mod"))
            card.download_btn.set_sensitive(bool(mod_item.props.download_url))
        overlay.set_tooltip_text(mod_item.props.short_description or None)

        pub_short, pub_full = format_relative_date(mod_item.props.created_at)
        card.published_label.set_text(pub_short)
        card.published_box.set_tooltip_text(_("Published: {date}").format(date=pub_full) if pub_full else None)

        upd_short, upd_full = format_relative_date(mod_item.props.updated_at)
        card.updated_label.set_text(upd_short)
        card.updated_box.set_tooltip_text(_("Updated: {date}").format(date=upd_full) if upd_full else None)

    def _on_open_page_clicked(self, mod_item: ModItem | None):
        if not mod_item or not mod_item.props.page_url:
            return
        parent = self.get_root()
        launcher = Gtk.UriLauncher.new(mod_item.props.page_url)
        launcher.launch(parent if isinstance(parent, Gtk.Window) else None, None, None)

    def _on_download_clicked(self, mod_item: ModItem | None):
        if not mod_item:
            return

        def _resolve_and_launch():
            if hasattr(self.provider, "get_protocol_download_url"):
                target_url = self.provider.get_protocol_download_url(mod_item)
            else:
                target_url = (mod_item.props.download_url or "").strip()

            GLib.idle_add(self._launch_protocol_url, mod_item, target_url)

        threading.Thread(target=_resolve_and_launch, daemon=True).start()

    def search_by_author(self, author: str):
        cleaned_author = (author or "").strip()
        if not cleaned_author:
            return

        include_adult = self.pop_adult_row.get_active()
        query = ""
        category = "All Categories"
        sort_by = self.sort_model.get_string(self.selected_sort_index) or "Most Downloaded first"
        date_range = (self.min_date, self.max_date)
        updated_range = (self.min_date, self.max_date)

        # Sync UI filter controls to reflect cleared non-adult filters
        self.compact_search_entry.set_text("")
        self.search_entry.set_text("")
        self.pop_category_row.set_selected(0)
        self.category_row.set_selected(0)
        self.pop_uploaded_slider.set_range_values(self.uploaded_date_slider.low_val, self.uploaded_date_slider.high_val)
        self.pop_updated_slider.set_range_values(self.updated_date_slider.low_val, self.updated_date_slider.high_val)

        self._current_author = cleaned_author
        self._current_search_params = (query, category, sort_by, date_range, updated_range, include_adult)
        self._next_offset = 0
        self._has_more = True

        results = self.provider.search_mods(
            query,
            category,
            sort_by,
            date_range,
            updated_range,
            include_adult,
            count=self._page_size,
            offset=0,
            author=cleaned_author,
        )

        self._raw_results = list(results)
        visible_mods = self._filter_mods(self._raw_results)

        self.model.remove_all()
        for mod in visible_mods:
            self.model.append(mod)

        self._next_offset = len(results)
        self._has_more = len(results) >= self._page_size

        self.header_controls_box.set_visible(True)
        self.stack.set_visible_child_name("browse")

    def _on_adult_row_toggled(self, row: Adw.SwitchRow, _pspec):
        if self._syncing:
            return

        new_val = bool(row.get_active())
        sibling = self.pop_adult_row if row is self.adult_row else self.adult_row

        self._syncing = True
        try:
            if sibling.get_active() != new_val:
                sibling.set_active(new_val)
        finally:
            self._syncing = False

        update_user_config("show_adult_mods_in_browse", new_val)

    def _on_hide_downloaded_toggled(self, row: Adw.SwitchRow, _pspec):
        if self._syncing:
            return

        new_val = bool(row.get_active())
        sibling = self.pop_hide_downloaded_row if row is self.hide_downloaded_row else self.hide_downloaded_row

        self._syncing = True
        try:
            if sibling.get_active() != new_val:
                sibling.set_active(new_val)
        finally:
            self._syncing = False

        update_user_config("hide_downloaded_mods", new_val)

        if self.stack.get_visible_child_name() == "browse":
            self._apply_downloaded_filter()

    def _filter_mods(self, mods: list[ModItem]) -> list[ModItem]:
        hide_downloaded = self.pop_hide_downloaded_row.get_active()
        if not hide_downloaded or not self._downloaded_mod_ids:
            return mods
        return [
            mod for mod in mods
            if str(mod.props.mod_id).strip() not in self._downloaded_mod_ids
        ]

    def _apply_downloaded_filter(self):
        visible_mods = self._filter_mods(self._raw_results)
        self.model.remove_all()
        for mod in visible_mods:
            self.model.append(mod)

    def _apply_thumbnail(self, card, mod_item: ModItem, expected_url: str, req_id: int, texture: Gdk.Texture | None):
        if card.current_mod is not mod_item:
            return False
        if getattr(card, "_thumb_request_id", None) != req_id:
            return False
        if (mod_item.props.thumbnail_url or "") != expected_url:
            return False

        if texture is not None:
            card.picture.set_paintable(texture)
            card.picture.set_visible(True)
            card.fallback_icon.set_visible(False)
        else:
            card.picture.set_paintable(None)
            card.picture.set_visible(False)
            card.fallback_icon.set_visible(True)
        return False

    def _launch_protocol_url(self, mod_item: ModItem, target_url: str):
        if not target_url:
            print(f"No download URL available for '{mod_item.props.name}'")
            return False

        parent = self.get_root()
        launcher = Gtk.UriLauncher.new(target_url)
        launcher.launch(parent if isinstance(parent, Gtk.Window) else None, None, None)
        return False


class ModBrowserWindow(Adw.Window):
    def __init__(
        self,
        parent_window: Gtk.Window,
        game_info: dict,
        headers: dict,
        downloads_metadata_path: str
    ):
        super().__init__()
        self.game_info = game_info or {}
        self.headers = dict(headers) if headers else {}
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_hide_on_close(True)
        self.set_default_size(950, 650)
        self.downloads_metadata_path = downloads_metadata_path

        game_name = self.game_info.get("name") or self.game_info.get("title")
        title = f"Universal Mod Browser — {game_name}" if game_name else "Universal Mod Browser"
        self.set_title(title)

        self.stores = self._build_supported_stores(self.game_info, self.headers)
        downloaded_mod_ids = load_downloaded_mod_ids(self.downloads_metadata_path)

        self.content_stack = Adw.ViewStack()
        self.store_views = {}
        for store_name, provider in self.stores.items():
            view = StoreView(provider, self.game_info, downloaded_mod_ids=downloaded_mod_ids)
            self.content_stack.add_named(view, store_name)
            self.store_views[store_name] = view

        if not self.stores:
            empty_box = Adw.StatusPage(
                icon_name="dialog-warning-symbolic",
                title="No Mod Platforms Supported",
                description="This game does not have a Nexus Mods or GameBanana ID configured.",
            )
            self.set_content(empty_box)
            return

        if len(self.stores) == 1:
            only_store = next(iter(self.stores))
            self.content_stack.set_visible_child_name(only_store)
            self.set_content(self.content_stack)
            return

        split_view = Adw.NavigationSplitView()
        split_view.set_min_sidebar_width(64)
        split_view.set_max_sidebar_width(80)

        sidebar_page = Adw.NavigationPage(title="Mod Platforms")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_title(False)
        sidebar_box.append(sidebar_header)

        store_list_box = Gtk.ListBox()
        store_list_box.add_css_class("navigation-sidebar")

        for store_name in self.stores.keys():
            row = Gtk.ListBoxRow()

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            box.set_margin_top(14)
            box.set_margin_bottom(14)
            box.set_margin_start(4)
            box.set_margin_end(4)
            box.set_halign(Gtk.Align.CENTER)

            icon_name = f"{store_name.lower().replace(' ', '-')}-logo"
            image = Gtk.Image.new_from_icon_name(icon_name)
            image.set_pixel_size(24)
            box.append(image)

            row.set_child(box)
            row.store_name = store_name
            row.set_tooltip_text(store_name)
            store_list_box.append(row)

        sidebar_box.append(store_list_box)
        sidebar_page.set_child(sidebar_box)
        split_view.set_sidebar(sidebar_page)

        content_page = Adw.NavigationPage(title="Mod Browser")
        content_page.set_child(self.content_stack)
        split_view.set_content(content_page)

        store_list_box.connect("row-selected", self.on_store_selected)

        self.set_content(split_view)

        store_list_box.select_row(store_list_box.get_row_at_index(0))

    @staticmethod
    def _build_supported_stores(
        game_info: dict,
        headers: dict | None = None,
    ) -> dict[str, BaseModProvider]:
        stores: dict[str, BaseModProvider] = {}
        if game_info.get("gamebanana_id"):
            stores["GameBanana"] = GameBananaModProvider(game_info, headers=headers)
        if game_info.get("nexus_id"):
            stores["Nexus"] = NexusModProvider(game_info, headers=headers)
        if game_info.get("thunderstore_id") or game_info.get("thunderstore_slug"):
            stores["Thunderstore"] = StoreProvider("Thunderstore", game_info, headers=headers)
        return stores

    def on_store_selected(self, box, row):
        if not row:
            return
        store_name = getattr(row, 'store_name', None)
        if store_name:
            self.content_stack.set_visible_child_name(store_name)
