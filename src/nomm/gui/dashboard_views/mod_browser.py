import cairo
import time
from gi.repository import Gtk, Adw, Gio, GObject, Gdk


class ModItem(GObject.Object):
    __gtype_name__ = 'ModItem'

    name = GObject.Property(type=str, default="")
    author = GObject.Property(type=str, default="")
    thumbnail_url = GObject.Property(type=str, default="")
    short_description = GObject.Property(type=str, default="")
    downloads = GObject.Property(type=int, default=0)
    endorsements = GObject.Property(type=int, default=0)

    def __init__(self, name="", uploader="", thumbnail_url="", downloads=0, endorsements=0, short_description=""):
        super().__init__()
        self.props.name = name
        self.props.author = uploader
        self.props.thumbnail_url = thumbnail_url
        self.props.downloads = downloads
        self.props.endorsements = endorsements
        self.props.short_description = short_description


class BaseModProvider:
    """Agnostic interface for mod websites (GameBanana, Nexus, Thunderstore)."""
    def search_mods(self, query: str, category: str, date_range: tuple, include_adult: bool) -> list[ModItem]:
        raise NotImplementedError

    def get_browse_mods(self) -> list[ModItem]:
        raise NotImplementedError

    # TODO: Add method to get first mod date
    def get_first_mod_date(self) -> float:
        raise NotImplementedError


class StoreProvider(BaseModProvider):
    def __init__(self, store_name: str):
        self.store_name = store_name

    def search_mods(self, query: str, category: str, date_range: tuple, include_adult: bool) -> list[ModItem]:
        print(f"Searching {self.store_name}: query='{query}', category='{category}', date_range='{date_range}', adult={include_adult}")
        return [
            ModItem(name=f"{self.store_name} Result: {query or 'All'} #{i}", uploader=f"Author {i}")
            for i in range(1, 13)
        ]

    def get_browse_mods(self) -> list[ModItem]:
        return [
            ModItem(f"{self.store_name} Trending Mod #{i}", f"Author {i}", "")
            for i in range(1, 25)
        ]

    # TODO: Implement the first mod retrieval method for this specific game and platform
    def get_first_mod_date(self) -> float:
        # Placeholder returning a timestamp representing the first mod upload date (e.g., Jan 1, 2015)
        return 1420070400


class DualRangeSlider(Gtk.Box):
    """A custom GTK4 slider widget featuring two points (low and high thumbs)."""
    def __init__(self, min_val: float, max_val: float):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.min_val = min_val
        self.max_val = max_val
        self.low_val = min_val
        self.high_val = max_val

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_size_request(240, 36)
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_draw_func(self.on_draw)

        # Drag gesture controller for interacting with the thumbs
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

    def _get_range_text(self) -> str:
        import datetime
        try:
            d_low = datetime.datetime.fromtimestamp(self.low_val).strftime('%Y-%m-%d')
            d_high = datetime.datetime.fromtimestamp(self.high_val).strftime('%Y-%m-%d')
            return f"{d_low} to {d_high}"
        except Exception:
            return f"{int(self.low_val)} - {int(self.high_val)}"

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

        cr.set_source_rgb(0.21, 0.52, 0.89)  # Adwaita accent blue (#3584e4)
        cr.set_line_width(6)
        cr.move_to(low_x, y)
        cr.line_to(high_x, y)
        cr.stroke()

        # 3. Thumbs (Low and High points)
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

        # Decide whether to drag the low or high thumb based on proximity
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
            new_val = max(self.min_val, min(new_val, self.high_val))
            self.low_val = new_val
        elif self.active_thumb == 'high':
            new_val = self.start_high + delta_val
            new_val = max(self.low_val, min(new_val, self.max_val))
            self.high_val = new_val

        self.label.set_text(self._get_range_text())
        self.drawing_area.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        self.active_thumb = None


class StoreView(Gtk.Box):
    def __init__(self, provider: BaseModProvider):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.provider = provider
        self.model = Gio.ListStore(item_type=ModItem)

        for mod in self.provider.get_browse_mods():
            self.model.append(mod)
        self.stack = Adw.ViewStack()

        search_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        search_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        search_page_box.set_valign(Gtk.Align.CENTER)
        search_page_box.set_halign(Gtk.Align.CENTER)
        search_page_box.set_size_request(500, -1)
        search_page_box.set_margin_top(24)
        search_page_box.set_margin_bottom(24)
        search_page_box.set_margin_start(24)
        search_page_box.set_margin_end(24)

        filter_group = Adw.PreferencesGroup(title="Search & Filters", description="Customize your mod search parameters")

        self.search_row = Adw.EntryRow(title="Search Query")
        self.search_row.connect("apply", lambda *_: self.execute_search())
        filter_group.add(self.search_row)

        categories_model = Gtk.StringList.new(["All Categories", "Gameplay", "Visuals", "Audio", "Tools"])
        self.category_row = Adw.ComboRow(title="Category", model=categories_model)
        filter_group.add(self.category_row)

        # Dual-point date range slider (min date set to first mod date, max to current time)
        min_date = self.provider.get_first_mod_date()
        max_date = time.time()  # Dynamically uses the current timestamp

        self.date_slider = DualRangeSlider(min_date, max_date)
        date_row = Adw.ActionRow(title="Date Range")
        date_row.set_subtitle("Select publication date range")
        date_row.add_suffix(self.date_slider)
        filter_group.add(date_row)

        self.adult_row = Adw.SwitchRow(title="Include Adult Content", subtitle="Show mods flagged as NSFW")
        filter_group.add(self.adult_row)

        search_page_box.append(filter_group)

        search_btn = Gtk.Button(label="Search Mods")
        search_btn.add_css_class("pill")
        search_btn.add_css_class("suggested-action")
        search_btn.set_halign(Gtk.Align.CENTER)
        search_btn.set_margin_top(12)
        search_btn.connect("clicked", lambda *_: self.execute_search())
        search_page_box.append(search_btn)

        search_scroll.set_child(search_page_box)
        self.stack.add_titled_with_icon(search_scroll, "search", "Search", "system-search-symbolic")

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
        browse_box.append(scrolled)

        self.stack.add_titled_with_icon(browse_box, "browse", "Browse", "view-grid-symbolic")

        header = Adw.HeaderBar()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        self.append(header)
        self.append(self.stack)

    def execute_search(self):
        query = self.search_row.get_text().strip()

        category_item = self.category_row.get_selected_item()
        category = category_item.get_string() if category_item else "All Categories"

        date_range = (self.date_slider.low_val, self.date_slider.high_val)
        include_adult = self.adult_row.get_active()

        results = self.provider.search_mods(query, category, date_range, include_adult)

        self.model.remove_all()
        for mod in results:
            self.model.append(mod)

        self.stack.set_visible_child_name("browse")

    def on_factory_setup(self, factory, list_item):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")
        card.set_size_request(160, 200)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.set_margin_start(8)
        card.set_margin_end(8)

        image = Gtk.Image(icon_name="application-x-addon-symbolic", pixel_size=64)
        image.set_vexpand(True)
        card.append(image)

        title_label = Gtk.Label(ellipsize=3)
        title_label.add_css_class("heading")
        card.append(title_label)

        author_label = Gtk.Label()
        author_label.add_css_class("dim-label")
        card.append(author_label)

        list_item.set_child(card)

    def on_factory_bind(self, factory, list_item):
        card = list_item.get_child()
        mod_item = list_item.get_item()

        children = []
        child = card.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()

        children[1].set_text(mod_item.props.name)
        children[2].set_text(mod_item.props.author)


class ModBrowserWindow(Adw.Window):
    def __init__(self, parent_window: Gtk.Window):
        super().__init__()
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_default_size(950, 650)
        self.set_title("Universal Mod Browser")

        split_view = Adw.NavigationSplitView()
        split_view.set_min_sidebar_width(64)
        split_view.set_max_sidebar_width(80)

        sidebar_page = Adw.NavigationPage(title="Stores")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        sidebar_header = Adw.HeaderBar()
        sidebar_box.append(sidebar_header)

        store_list_box = Gtk.ListBox()
        store_list_box.add_css_class("navigation-sidebar")

        self.stores = {
            "GameBanana": StoreProvider("GameBanana"),
            "Nexus": StoreProvider("Nexus Mods"),
            "Thunderstore": StoreProvider("Thunderstore"),
        }

        for store_name in self.stores.keys():
            row = Gtk.ListBoxRow()

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            box.set_margin_top(14)
            box.set_margin_bottom(14)
            box.set_margin_start(4)
            box.set_margin_end(4)
            box.set_halign(Gtk.Align.CENTER)

            # Map store name to gresource icon name (e.g., "gamebanana-symbolic", "nexus-mods-symbolic", etc.)
            icon_name = f"{store_name.lower().replace(' ', '-')}-logo"
            image = Gtk.Image.new_from_icon_name(icon_name)
            image.set_pixel_size(24)
            box.append(image)

            row.set_child(box)
            row.store_name = store_name
            row.set_tooltip_text(store_name)  # Tooltip shows the store name on hover/accessibility
            store_list_box.append(row)

        sidebar_box.append(store_list_box)
        sidebar_page.set_child(sidebar_box)
        split_view.set_sidebar(sidebar_page)

        self.content_stack = Adw.ViewStack()

        self.store_views = {}
        for store_name, provider in self.stores.items():
            view = StoreView(provider)
            self.content_stack.add_named(view, store_name)
            self.store_views[store_name] = view

        content_page = Adw.NavigationPage(title="Mod Browser")
        content_page.set_child(self.content_stack)
        split_view.set_content(content_page)

        store_list_box.connect("row-selected", self.on_store_selected)

        self.set_content(split_view)

        store_list_box.select_row(store_list_box.get_row_at_index(0))

    def on_store_selected(self, box, row):
        if not row:
            return
        store_name = getattr(row, 'store_name', None)
        if store_name:
            self.content_stack.set_visible_child_name(store_name)