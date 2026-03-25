#!/usr/bin/env bash
# scripts/build-image.sh — costruisce l'immagine pi-Mesh in CI
# Usage: sudo bash scripts/build-image.sh <base.img> <output.img> <tag>
set -euo pipefail

BASE_IMG="$1"
OUT_IMG="$2"
TAG="${3:-master}"
REPO_URL="https://github.com/yayoboy/pi-Mesh.git"

echo "Copia immagine base..."
cp "$BASE_IMG" "$OUT_IMG"

echo "Espansione immagine (+2 GB)..."
truncate -s +2G "$OUT_IMG"
parted -s "$OUT_IMG" resizepart 2 100%
LOOP=$(losetup --find --show --partscan "$OUT_IMG")
e2fsck -f "${LOOP}p2" || true
resize2fs "${LOOP}p2"

echo "Mount partizioni..."
BOOT_MNT=$(mktemp -d)
ROOT_MNT=$(mktemp -d)
mount "${LOOP}p1" "$BOOT_MNT"
mount "${LOOP}p2" "$ROOT_MNT"

echo "Abilita SSH e imposta password..."
touch "$BOOT_MNT/ssh"

echo "Setup QEMU per ARM in chroot..."
cp /usr/bin/qemu-aarch64-static "$ROOT_MNT/usr/bin/"

echo "Monta bind per chroot..."
mount --bind /dev  "$ROOT_MNT/dev"
mount --bind /proc "$ROOT_MNT/proc"
mount --bind /sys  "$ROOT_MNT/sys"

echo "Esegui install.sh in chroot..."
chroot "$ROOT_MNT" /bin/bash -c "
  set -e
  apt-get update -qq
  apt-get install -y -qq git curl python3-venv python3-pip pigpiod avahi-daemon
  git clone --branch '${TAG}' --depth 1 '${REPO_URL}' /home/pi/pi-mesh
  INSTALL_DIR=/home/pi/pi-mesh BRANCH='${TAG}' \
    bash /home/pi/pi-mesh/install.sh --non-interactive --no-zram
  chown -R 1000:1000 /home/pi/pi-mesh
  echo 'pi-mesh' > /etc/hostname
  sed -i 's/raspberrypi/pi-mesh/g' /etc/hosts
"

echo "Umount..."
umount "$ROOT_MNT/sys" "$ROOT_MNT/proc" "$ROOT_MNT/dev"
umount "$BOOT_MNT" "$ROOT_MNT"
losetup -d "$LOOP"
rmdir "$BOOT_MNT" "$ROOT_MNT"

echo "Shrink immagine con pishrink..."
if ! command -v pishrink.sh &>/dev/null; then
  wget -q -O /usr/local/bin/pishrink.sh \
    https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
  chmod +x /usr/local/bin/pishrink.sh
fi
pishrink.sh "$OUT_IMG"

echo "Immagine pronta: $OUT_IMG"
