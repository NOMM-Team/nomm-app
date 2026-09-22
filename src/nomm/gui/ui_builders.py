from gi.repository import Gtk, Gio


def create_text_box(text: str, type="", url="") -> Gtk.Widget:
    """creates a stylised text box. Type can be either info or warning. if URL provided, box will be clickable."""
    text_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)

    if type in ["warning", "info"]:
        text_box.add_css_class(f"{type}-card")
        icon = Gtk.Image.new_from_icon_name(f"mat-{type}-symbolic")
        icon.set_valign(Gtk.Align.CENTER)
        icon.set_pixel_size(24)
        text_box.append(icon)

    label = Gtk.Label(label=text, wrap=True, max_width_chars=50, justify=Gtk.Justification.CENTER, use_markup=True)
    label.set_valign(Gtk.Align.CENTER)
    text_box.append(label)

    if url:
        button = Gtk.Button(child=text_box, halign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        button.add_css_class("activatable")
        button.set_cursor_from_name("pointer")

        button.connect("clicked", lambda _: Gio.AppInfo.launch_default_for_uri(url, None))
        return button

    return text_box
