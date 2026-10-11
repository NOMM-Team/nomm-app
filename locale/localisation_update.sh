# Update the template
find src/nomm -name "*.py" | xgettext -L Python -k_ -o locale/moe.nomm.Nomm.pot -f -
# Merge new strings into the translation files without losing old ones
msgmerge --update locale/fr.po locale/moe.nomm.Nomm.pot

# To test a localisation run "flatpak run --env=LC_ALL=fr_FR.UTF-8 moe.nomm.Nomm" and replace fr_FR with your language (i.e. de_DE, it_IT, es_ES, zh_CN, etc.)