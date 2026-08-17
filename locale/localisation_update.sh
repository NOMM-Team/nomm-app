# Update the template
xgettext --from-code=UTF-8 --language=Python --keyword=_ --output=locale/moe.nomm.Nomm.pot src/*.py src/core/*.py src/gui/*py src/gui/app_views/*.py src/gui/dashboard_views/*.py

# Merge new strings into the translation files without losing old ones
msgmerge --update locale/fr.po locale/moe.nomm.Nomm.pot

# To test a localisation run "flatpak run --env=LC_ALL=fr_FR.UTF-8 moe.nomm.Nomm" and replace fr_FR with your language (i.e. de_DE, it_IT, es_ES, zh_CN, etc.)