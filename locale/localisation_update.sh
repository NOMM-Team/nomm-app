# Update the template
xgettext --from-code=UTF-8 --language=Python --keyword=_ --output=locale/com.nomm.Nomm.pot src/*.py

# Merge new strings into the translation files without losing old ones
msgmerge --update locale/fr.po locale/com.nomm.Nomm.pot

# To test a localisation run "flatpak run --env=LC_ALL=fr_FR.UTF-8 com.nomm.Nomm" and replace fr_FR with your language (i.e. de_DE, it_IT, es_ES, zh_CN, etc.)