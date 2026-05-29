#!/bin/bash

# Build flatpak
if [ $1 == "flatpak" ]; then
    ./build/flatpak/build-flatpak.sh
fi

# Build AUR package
if [ $1 == "aur" ]; then
    cd "$(dirname "$0")/aur"
    makepkg -si
fi