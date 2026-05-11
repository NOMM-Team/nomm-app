import webbrowser
import gi
from gi.repository import Gtk, Adw

class TextWindow(Adw.Window):
    def __init__(self, parent, title, content, text_type="text"):
        # We set the internal window title, though the HeaderBar will display the WindowTitle widget
        super().__init__(transient_for=parent, modal=True)
        
        self.set_default_size(570, 490)
        
        # Root Container
        root_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_container)

        # Adwaita HeaderBar
        header_bar = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(
            title=_(f"NOMM Reader: {title}"),
        )
        header_bar.set_title_widget(self.title_widget)
        root_container.append(header_bar)
        
        # Body
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.add_css_class('tw-body')
        body_content = Gtk.Label(xalign=0, wrap=True)
        if text_type == "text":
            body_content.set_label(content)
        if text_type == "markup":
            body_content.set_markup(content)
            body_content.connect("activate-link", lambda label, uri: webbrowser.open(uri))
        body_content.add_css_class('tw-body-content')
        body_content.set_valign(Gtk.Align.START)
        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add_css_class("tw-scrolled")
        scrolled.set_child(body_content)
        body.append(scrolled)

        root_container.append(body)
