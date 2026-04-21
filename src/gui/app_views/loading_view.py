import gettext

from gi.repository import Gtk

_ = gettext.gettext

class LoadingView(Gtk.Box):
    def __init__(self, message=_("Loading..."), spinner_size=64):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.CENTER)
        
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(spinner_size, spinner_size)
        self.spinner.start()
        
        self.label = Gtk.Label(label=message)
        self.label.add_css_class("title-2")
        
        self.append(self.spinner)
        self.append(self.label)

    def set_message(self, message):
        """Permet de changer le texte dynamiquement si besoin."""
        self.label.set_label(message)