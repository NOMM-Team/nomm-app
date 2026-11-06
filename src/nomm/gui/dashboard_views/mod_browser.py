from gi.repository import Gtk, Adw, Gio, GObject


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
    def search_mods(self, query: str, category: str, date_range: str, include_adult: bool) -> list[ModItem]:
        raise NotImplementedError

    def get_browse_mods(self) -> list[ModItem]:
        raise NotImplementedError


class StoreProvider(BaseModProvider):
    def __init__(self, store_name: str):
        self.store_name = store_name

    def search_mods(self, query: str, category: str, date_range: str, include_adult: bool) -> list[ModItem]:
        print(f"Searching {self.store_name}: query='{query}', category='{category}', date='{date_range}', adult={include_adult}")
        return [
            ModItem(name=f"{self.store_name} Result: {query or 'All'} #{i}", uploader=f"Author {i}")
            for i in range(1, 13)
        ]

    def get_browse_mods(self) -> list[ModItem]:
        return [
            ModItem(f"{self.store_name} Trending Mod #{i}", f"Author {i}", "")
            for i in range(1, 25)
        ]


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

        dates_model = Gtk.StringList.new(["Any Time", "Past 24 Hours", "Past Week", "Past Month", "Past Year"])
        self.date_row = Adw.ComboRow(title="Date Range", model=dates_model)
        filter_group.add(self.date_row)

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

        date_item = self.date_row.get_selected_item()
        date_range = date_item.get_string() if date_item else "Any Time"

        include_adult = self.adult_row.get_active()

        results = self.provider.search_mods(query, category, date_range, include_adult)

        self.model.remove_all()
        for mod in results:
            self.model.append(mod)

        self.stack.set_visible_child_name("browse")

    def on_search_activated(self, entry):
        # Optional live search debounce or handling can go here
        pass

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

        # children[0] = Image, children[1] = Title, children[2] = Author
        children[1].set_text(mod_item.data.name)
        children[2].set_text(mod_item.data.author)


class ModBrowserWindow(Adw.Window):
    def __init__(self, parent_window: Gtk.Window):
        super().__init__()
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_default_size(950, 650)
        self.set_title("Universal Mod Browser")

        split_view = Adw.NavigationSplitView()

        sidebar_page = Adw.NavigationPage(title="Stores")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        sidebar_header = Adw.HeaderBar()
        sidebar_box.append(sidebar_header)

        store_list_box = Gtk.ListBox()
        store_list_box.add_css_class("navigation-sidebar")

        self.stores = {
            "GameBanana": StoreProvider("GameBanana"),
            "Nexus Mods": StoreProvider("Nexus Mods"),
            "Thunderstore": StoreProvider("Thunderstore"),
        }

        for store_name in self.stores.keys():
            row = Adw.ActionRow(title=store_name)
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
        store_name = row.get_title()
        self.content_stack.set_visible_child_name(store_name)
