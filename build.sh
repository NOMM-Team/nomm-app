# flatpak-pip-generator is a tool that helps handle complex library/dependency requirements.
# You give it the libraries you need to package and it generates a python3-modules.json for you with all the libraries you need

curl -L https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/refs/heads/master/pip/flatpak-pip-generator.py -o flatpak-pip-generator.py

python3 flatpak-pip-generator.py requests PyYAML vdf rarfile

# Build the flatpak folders and files. This uses the standard flatpak-builder utility
flatpak-builder --user --install --force-clean --repo=repo build-dir com.nomm.Nomm.yaml

# Once you have all the files/folders generated, you package it into a neat little flatpak file :)
flatpak build-bundle ./repo NOMM.flatpak com.nomm.Nomm