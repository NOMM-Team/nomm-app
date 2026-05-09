import gi
from gi.repository import Gtk, Adw

class TextWindow(Adw.Window):
    def __init__(self, parent, title, content):
        # We set the internal window title, though the HeaderBar will display the WindowTitle widget
        super().__init__(transient_for=parent, modal=True)
        
        self.set_default_size(570, 490)
        
        # 1. Root Container
        root_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_container)

        # 2. Adwaita HeaderBar
        header_bar = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(
            title=_(f"NOMM Reader: {title}"),
        )
        header_bar.set_title_widget(self.title_widget)
        root_container.append(header_bar)

        # 3. Content Area (Body & Footer)
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_area.add_css_class('tw-content-area')
        root_container.append(content_area)
        
        # Body
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.add_css_class('tw-body')
        
        body_content = Gtk.Label(label=content, xalign=0, wrap=True)
        body_content.add_css_class('tw-body-content')
        body_content.set_valign(Gtk.Align.START)
        #body_content.set_margin_all(12)
        
        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add_css_class("tw-scrolled")
        scrolled.set_child(body_content)
        body.append(scrolled)

        content_area.append(body)
