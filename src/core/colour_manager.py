from gi.repository import GLib, Gtk, Gdk

def set_accent_colour(accent_colour: str, _accent_style_provider):
    reset_accent_colour(_accent_style_provider)

    print(f"Applying new custom accent color: {accent_colour}")
    fg_color = get_contrast_color(accent_colour)

    css = f"""
    window {{
        --accent-bg-color: {accent_colour};
        --accent-color: {accent_colour};
        --accent-fg-color: {fg_color};
    }}
    """

    _accent_style_provider = Gtk.CssProvider()
    _accent_style_provider.load_from_data(css.encode())

    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        _accent_style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    return _accent_style_provider

def reset_accent_colour(_accent_style_provider):
    """Reverts the application back to the default system Libadwaita accent color."""

    if _accent_style_provider is not None:
        print("Reverting to default system accent color")

        Gtk.StyleContext.remove_provider_for_display(
            Gdk.Display.get_default(), _accent_style_provider
        )

        _accent_style_provider = None

def get_contrast_color(hex_code: str) -> str:
    hex_code = hex_code.lstrip('#')
    
    r, g, b = [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
    
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    
    return "#000000" if luminance > 0.5 else "#ffffff"
