import gettext
import cairo
import time
import datetime
from gi.repository import Gtk, Adw, Gio, GObject, Gdk
from nomm.gui.ui_builders import create_icon_button
from nomm.core.tools import format_count
from nomm.core.user_config import load_user_config, update_user_config
from nomm.platforms.nexus import search_nexus_mods, get_nexus_first_mod_date

_ = gettext.gettext


class ModItem(GObject.Object):
    __gtype_name__ = 'ModItem'

    name = GObject.Property(type=str, default="")
    author = GObject.Property(type=str, default="")
    thumbnail_url = GObject.Property(type=str, default="")
    short_description = GObject.Property(type=str, default="")
    page_url = GObject.Property(type=str, default="")
    download_url = GObject.Property(type=str, default="")
    downloads = GObject.Property(type=int, default=0)
    endorsements = GObject.Property(type=int, default=0)

    def __init__(
        self,
        name="",
        uploader="",
        thumbnail_url="",
        downloads=0,
        endorsements=0,
        short_description="",
        page_url="",
        download_url="",
    ):
        super().__init__()
        self.props.name = name
        self.props.author = uploader
        self.props.thumbnail_url = thumbnail_url
        self.props.downloads = downloads
        self.props.endorsements = endorsements
        self.props.short_description = short_description
        self.props.page_url = page_url
        self.props.download_url = download_url


class BaseModProvider:
    """Agnostic interface for mod websites (GameBanana, Nexus, Thunderstore)."""
    def search_mods(self, query: str, category: str, sort_by: str, date_range: tuple, include_adult: bool,
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

    def search_mods(self, query: str, category: str, sort_by: str, date_range: tuple, include_adult: bool,
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
                downloads=item["downloads"],
                endorsements=item["endorsements"],
                short_description=item["short_description"],
                page_url=item["page_url"],
                download_url=item["download_url"],
            )
            for item in raw_results
        ]

    def get_browse_mods(self) -> list[ModItem]:
        return self.search_mods(
            query="",
            category="All Categories",
            sort_by="Most Downloaded first",
            date_range=(self.get_first_mod_date(), time.time()),
            include_adult=False,
        )


class StoreProvider(BaseModProvider):
    def __init__(self, store_name: str, game_info: dict | None = None, headers: dict | None = None):
        self.store_name = store_name
        self.headers = dict(headers) if headers else {}
        self.game_info = game_info or {}

    def _slug(self) -> str:
        return self.store_name.lower().replace(" ", "-")

    def search_mods(self, query: str, category: str, sort_by: str, date_range: tuple, include_adult: bool) -> list[ModItem]:
        print(
            f"Searching {self.store_name}: query='{query}', category='{category}', "
            f"sort='{sort_by}', date_range='{date_range}', adult={include_adult}"
        )
        slug = self._slug()
        return [
            ModItem(
                name=f"{self.store_name} Result: {query or 'All'} #{i}",
                uploader=f"Author {i}",
                downloads=i * 14500,
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
            d_low = datetime.datetime.fromtimestamp(self.low_val).strftime('%Y-%m-%d')
            if abs(self.high_val - self.max_val) < 1.0:
                d_high = "now"
            else:
                d_high = datetime.datetime.fromtimestamp(self.high_val).strftime('%Y-%m-%d')
            return _(f"{d_low} to {d_high}")
        except Exception:
            high_str = "now" if abs(self.high_val - self.max_val) < 1.0 else str(int(self.high_val))
            return f"{int(self.low_val)} - {high_str}"

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


class StoreView(Gtk.Box):
    def __init__(self, provider: BaseModProvider, game_info: dict | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.provider = provider
        self.game_info = game_info or {}
        self.model = Gio.ListStore(item_type=ModItem)
        self._syncing = False
        self._page_size = 20
        self._next_offset = 0
        self._loading_more = False
        self._has_more = True
        self._current_search_params: tuple | None = None

        user_cfg = load_user_config() or {}
        self._include_adult_default = bool(user_cfg.get("show_adult_mods_in_browse", False))

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

        pop_group = Adw.PreferencesGroup()

        self.pop_category_row = Adw.ComboRow(title="Category", model=self.categories_model)
        pop_group.add(self.pop_category_row)

        self.pop_date_slider = DualRangeSlider(self.min_date, self.max_date)
        pop_date_row = Adw.ActionRow(title="Date Range")
        pop_date_row.set_subtitle("Publication date")
        pop_date_row.add_suffix(self.pop_date_slider)
        pop_group.add(pop_date_row)

        self.pop_adult_row = Adw.SwitchRow(title="Include Adult Content")
        self.pop_adult_row.set_active(self._include_adult_default)
        self.pop_adult_row.connect("notify::active", self._on_adult_row_toggled)
        pop_group.add(self.pop_adult_row)

        pop_box.append(pop_group)

        apply_btn = Gtk.Button(label="Apply Filters")
        apply_btn.add_css_class("suggested-action")
        apply_btn.add_css_class("pill")
        apply_btn.connect("clicked", lambda *_: (filter_popover.popdown(), self.execute_search(from_compact=True)))
        pop_box.append(apply_btn)

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

        filter_group = Adw.PreferencesGroup()

        self.category_row = Adw.ComboRow(title="Category", model=self.categories_model)
        filter_group.add(self.category_row)

        self.sort_row = Adw.ComboRow(title="Sort by", model=self.sort_model)
        filter_group.add(self.sort_row)

        self.date_slider = DualRangeSlider(self.min_date, self.max_date)
        date_row = Adw.ActionRow(title="Date Range")
        date_row.set_subtitle("Select publication date range")
        date_row.add_suffix(self.date_slider)
        filter_group.add(date_row)

        self.adult_row = Adw.SwitchRow(title="Include Adult Content", subtitle="Show mods flagged as NSFW")
        self.adult_row.set_active(self._include_adult_default)
        self.adult_row.connect("notify::active", self._on_adult_row_toggled)
        filter_group.add(self.adult_row)

        search_page_box.append(filter_group)
        search_scroll.set_child(search_page_box)

        self.stack.add_named(search_scroll, "search")

    def _build_browse_page(self):
        browse_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        self.selection_model = Gtk.NoSelection(model=self.model)
        self.grid_view = Gtk.GridView(model=self.selection_model, factory=factory)
        self.grid_view.set_max_columns(4)
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
            self.pop_date_slider.set_range_values(self.date_slider.low_val, self.date_slider.high_val)

        query = self.compact_search_entry.get_text().strip()

        category_item = self.pop_category_row.get_selected_item()
        category = category_item.get_string() if category_item else "All Categories"

        sort_by = self.sort_model.get_string(self.selected_sort_index) or "Most Downloaded first"

        date_range = (self.pop_date_slider.low_val, self.pop_date_slider.high_val)
        include_adult = self.pop_adult_row.get_active()

        self._current_search_params = (query, category, sort_by, date_range, include_adult)
        self._next_offset = 0
        self._has_more = True

        results = self.provider.search_mods(
            query,
            category,
            sort_by,
            date_range,
            include_adult,
            count=self._page_size,
            offset=0,
        )

        self.model.remove_all()
        for mod in results:
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
        try:
            query, category, sort_by, date_range, include_adult = self._current_search_params
            more_results = self.provider.search_mods(
                query,
                category,
                sort_by,
                date_range,
                include_adult,
                author=self._current_author,
                count=self._page_size,
                offset=self._next_offset
            )
            for mod in more_results:
                self.model.append(mod)

            self._next_offset += len(more_results)
            if len(more_results) < self._page_size:
                self._has_more = False
        finally:
            self._loading_more = False

    def on_factory_setup(self, factory, list_item):
        overlay = Gtk.Overlay()
        overlay.set_size_request(180, 220)
        overlay.set_margin_top(8)
        overlay.set_margin_bottom(8)
        overlay.set_margin_start(8)
        overlay.set_margin_end(8)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")
        card.set_hexpand(True)
        card.set_vexpand(True)
        card.current_mod = None
        card.overlay = overlay

        image = Gtk.Image(icon_name="nomm-logo", pixel_size=64)
        image.set_vexpand(True)
        card.append(image)

        title_label = Gtk.Label(ellipsize=3)
        title_label.add_css_class("heading")
        title_label.set_margin_start(8)
        title_label.set_margin_end(8)
        card.append(title_label)

        author_btn = Gtk.Button()
        author_btn.add_css_class("flat")
        author_btn.set_margin_start(8)
        author_btn.set_margin_end(8)
        author_btn.set_margin_bottom(10)

        author_label = Gtk.Label(ellipsize=3)
        author_label.add_css_class("dim-label")
        author_btn.set_child(author_label)

        def on_author_clicked(_btn, c=card):
            if c.current_mod and c.current_mod.props.author:
                self.search_by_author(c.current_mod.props.author)

        author_btn.connect("clicked", on_author_clicked)
        card.append(author_btn)

        overlay.set_child(card)

        stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        stats_box.set_halign(Gtk.Align.START)
        stats_box.set_valign(Gtk.Align.START)
        stats_box.set_margin_top(8)
        stats_box.set_margin_start(8)

        downloads_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        downloads_box.set_halign(Gtk.Align.START)
        downloads_icon = Gtk.Image.new_from_icon_name("downloaded-symbolic")
        downloads_icon.set_pixel_size(13)
        downloads_icon.add_css_class("dim-label")
        downloads_label = Gtk.Label(label="0")
        downloads_label.add_css_class("dim-label")
        downloads_label.add_css_class("caption")
        downloads_box.append(downloads_icon)
        downloads_box.append(downloads_label)

        endorsements_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        endorsements_box.set_halign(Gtk.Align.START)
        endorsements_icon = Gtk.Image.new_from_icon_name("mat-donate-symbolic")
        endorsements_icon.set_pixel_size(13)
        endorsements_icon.add_css_class("dim-label")
        endorsements_label = Gtk.Label(label="0")
        endorsements_label.add_css_class("dim-label")
        endorsements_label.add_css_class("caption")
        endorsements_box.append(endorsements_icon)
        endorsements_box.append(endorsements_label)

        stats_box.append(downloads_box)
        stats_box.append(endorsements_box)
        overlay.add_overlay(stats_box)

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

        card.title_label = title_label
        card.author_label = author_label
        card.downloads_box = downloads_box
        card.downloads_label = downloads_label
        card.endorsements_box = endorsements_box
        card.endorsements_label = endorsements_label
        card.download_btn = download_btn

        list_item.set_child(overlay)

    def on_factory_bind(self, factory, list_item):
        overlay = list_item.get_child()
        card = overlay.get_child()
        mod_item = list_item.get_item()

        card.current_mod = mod_item
        card.title_label.set_text(mod_item.props.name)
        card.author_label.set_text(mod_item.props.author)
        card.downloads_label.set_text(format_count(mod_item.props.downloads))
        card.downloads_box.set_tooltip_text(f"{mod_item.props.downloads:,} downloads")
        card.endorsements_label.set_text(format_count(mod_item.props.endorsements))
        card.endorsements_box.set_tooltip_text(f"{mod_item.props.endorsements:,} endorsements")
        card.download_btn.set_sensitive(bool(mod_item.props.download_url))
        overlay.set_tooltip_text(mod_item.props.short_description or None)

    def _on_open_page_clicked(self, mod_item: ModItem | None):
        if not mod_item or not mod_item.props.page_url:
            return
        parent = self.get_root()
        launcher = Gtk.UriLauncher.new(mod_item.props.page_url)
        launcher.launch(parent if isinstance(parent, Gtk.Window) else None, None, None)

    def _on_download_clicked(self, mod_item: ModItem | None):
        if not mod_item or not mod_item.props.download_url:
            return
        print(f"Downloading '{mod_item.props.name}' from {mod_item.props.download_url}")

    def search_by_author(self, author: str):
        cleaned_author = (author or "").strip()
        if not cleaned_author:
            return

        include_adult = self.pop_adult_row.get_active()
        query = ""
        category = "All Categories"
        sort_by = self.sort_model.get_string(self.selected_sort_index) or "Most Downloaded first"
        date_range = (self.min_date, self.max_date)

        # Sync UI filter controls to reflect cleared non-adult filters
        self.compact_search_entry.set_text("")
        self.search_entry.set_text("")
        self.pop_category_row.set_selected(0)
        self.category_row.set_selected(0)
        self.pop_date_slider.set_range_values(self.min_date, self.max_date)
        self.date_slider.set_range_values(self.min_date, self.max_date)

        self._current_author = cleaned_author
        self._current_search_params = (query, category, sort_by, date_range, include_adult)
        self._next_offset = 0
        self._has_more = True

        results = self.provider.search_mods(
            query,
            category,
            sort_by,
            date_range,
            include_adult,
            count=self._page_size,
            offset=0,
            author=cleaned_author,
        )

        self.model.remove_all()
        for mod in results:
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


class ModBrowserWindow(Adw.Window):
    def __init__(
        self,
        parent_window: Gtk.Window,
        game_info: dict | None = None,
        headers: dict | None = None,
    ):
        super().__init__()
        self.game_info = game_info or {}
        self.headers = dict(headers) if headers else {}
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_hide_on_close(True)
        self.set_default_size(950, 650)

        game_name = self.game_info.get("name") or self.game_info.get("title")
        title = f"Universal Mod Browser — {game_name}" if game_name else "Universal Mod Browser"
        self.set_title(title)

        self.stores = self._build_supported_stores(self.game_info, self.headers)

        self.content_stack = Adw.ViewStack()
        self.store_views = {}
        for store_name, provider in self.stores.items():
            view = StoreView(provider, self.game_info)
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
            stores["GameBanana"] = StoreProvider("GameBanana", game_info, headers=headers)
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
