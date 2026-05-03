import gi
from gi.repository import Gtk

class TextWindow(Gtk.Window):
    def __init__(self, parent, title, content):
        super().__init__(title=f"Text Reader: {title}",transient_for=parent, modal=False)
        
        self.set_default_size(570, 490)
        
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content_area.add_css_class('tw-content-area')
        
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.add_css_class('tw-header')
        
        header_icon = Gtk.Image.new_from_icon_name('games-config-tiles-symbolic')
        header_icon.add_css_class('tw-header-icon')
        header_icon.set_halign(Gtk.Align.START)
        
        window_title = Gtk.Label(label='Description')
        window_title.add_css_class('tw-title')
        window_title.set_hexpand(True)
        window_title.set_halign(Gtk.Align.CENTER)
        
        close_icon = Gtk.Button()
        close_icon.set_icon_name('window-close-symbolic')
        close_icon.connect('clicked', self.on_close_clicked)
        close_icon.add_css_class('tw-close-icon')
        close_icon.add_css_class('flat')
        close_icon.set_halign(Gtk.Align.END)
        
        header.append(header_icon)
        header.append(window_title)
        header.append(close_icon)
        
        # Body
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.add_css_class('tw-body')
        
        file_name = Gtk.Label(label=title, xalign=0, wrap=False)
        file_name.add_css_class('tw-file-name')
        file_name.set_margin_start(12)
        file_name.set_margin_end(12)
        file_name.set_margin_top(6)
        file_name.set_margin_bottom(6)
        
        v_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        
        body_content = Gtk.Label(label=content, xalign=0, wrap=True)
        body_content.add_css_class('tw-body-content')
        body_content.set_valign(Gtk.Align.START)
        
        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=False)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add_css_class("tw-scrolled")
        scrolled.set_child(body_content)
        
        body.append(file_name)
        body.append(v_separator)
        body.append(scrolled)
        
        # Footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.add_css_class('tw-footer')
        footer.set_hexpand(True)
 
        close_button = Gtk.Button(label='Close')
        close_button.connect('clicked', self.on_close_clicked)
        close_button.add_css_class('tw-close-btn')
        close_button.add_css_class('suggested-action')
        close_button.set_halign(Gtk.Align.END)
        close_button.set_hexpand(True)
        footer.append(close_button)

        
        content_area.append(header)
        content_area.append(body)
        content_area.append(footer)
        
        self.set_child(content_area)
        
    def on_close_clicked(self, button):
        self.close()