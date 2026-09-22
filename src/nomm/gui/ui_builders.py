from gi.repository import Gtk, Gio, GLib
from typing import Optional, Callable


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


def create_code_box(code: str, add_copy_button: bool = False) -> Gtk.Widget:

    text_view = Gtk.TextView()
    text_view.set_editable(False)
    text_view.set_cursor_visible(False)
    text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    text_view.set_monospace(True)
    text_view.add_css_class("card")

    buffer = text_view.get_buffer()
    buffer.set_text(code)

    text_view.set_size_request(450, 100)
    text_view.set_left_margin(10)
    text_view.set_right_margin(10)
    text_view.set_top_margin(10)
    text_view.set_bottom_margin(10)

    if not add_copy_button:
        return text_view

    overlay = Gtk.Overlay()
    overlay.set_child(text_view)

    copy_btn = Gtk.Button(
        icon_name="edit-copy-symbolic",
        halign=Gtk.Align.END,
        valign=Gtk.Align.END,
    )
    copy_btn.set_tooltip_text("Copy Contents")
    copy_btn.set_cursor_from_name("pointer")
    copy_btn.add_css_class("flat")

    copy_btn.set_margin_top(6)
    copy_btn.set_margin_end(6)

    def on_copy_clicked(_button):
        start, end = buffer.get_bounds()
        text_to_copy = buffer.get_text(start, end, True)
        clipboard = text_view.get_clipboard()
        clipboard.set(text_to_copy)

        copy_btn.set_icon_name("object-select-symbolic")
        GLib.timeout_add(
            1500, lambda: copy_btn.set_icon_name("edit-copy-symbolic")
        )

    copy_btn.connect("clicked", on_copy_clicked)

    overlay.add_overlay(copy_btn)

    return overlay


def create_icon_button(
    *,
    icon_name: str,
    tooltip: str,
    icon_size: int = 24,
    icon_margin: int = 2,
    valign: Gtk.Align = Gtk.Align.CENTER,
    halign: Gtk.Align = Gtk.Align.END,
    css_classes: Optional[list[str]] = None,
    on_click: Optional[Callable] = None,
    hover_mouse_pointer: bool = True,
    disabled: bool = False
) -> Gtk.Button:

    button = Gtk.Button(valign=valign, halign=halign)
    button.add_css_class("image-button")

    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_pixel_size(icon_size)
    img.set_valign(Gtk.Align.CENTER)
    img.set_halign(Gtk.Align.CENTER)
    img.set_margin_start(icon_margin)
    img.set_margin_end(icon_margin)
    img.set_margin_top(icon_margin)
    img.set_margin_bottom(icon_margin)
    button.set_child(img)

    button.set_tooltip_text(tooltip)
    if hover_mouse_pointer:
        button.set_cursor_from_name("pointer")

    if disabled:
        button.set_sensitive(False)

    classes_to_add = css_classes if css_classes is not None else ["flat"]
    for css_class in classes_to_add:
        button.add_css_class(css_class)

    if on_click:
        button.connect("clicked", on_click)

    return button
