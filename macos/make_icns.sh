#!/bin/bash
# Иконка бандла JobBot.icns из client/icon.png — в build/, в дерево не кладётся.
#
# Исходник не квадратный, а iconutil берёт только квадраты: он дополняется
# до квадрата полями, а не растягивается.
set -euo pipefail

src=client/icon.png
set_dir=build/JobBot.iconset
rm -rf "$set_dir"
mkdir -p "$set_dir"

side=$(sips -g pixelWidth -g pixelHeight "$src" | awk '/pixel/ {print $2}' | sort -n | tail -1)
sips -p "$side" "$side" "$src" --out build/icon-square.png >/dev/null

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" build/icon-square.png --out "$set_dir/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" build/icon-square.png --out "$set_dir/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns -o build/JobBot.icns "$set_dir"
