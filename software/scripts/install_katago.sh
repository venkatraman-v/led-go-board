#!/usr/bin/env bash
# Installs the KataGo pieces used by the LED Go board:
#   - checks for the katago executable
#   - downloads a b18c384nbt network (compatible with KataGo 1.14+)
#   - installs a GTP config with logs under ~/.katago/logs
#   - installs pyserial for the optional LED serial transport
#
# Everything is user-local.  If KataGo itself is missing, the script prints the
# system package command instead of running sudo for you.
set -euo pipefail

KATAGO_DIR="${KATAGO_DIR:-$HOME/.katago}"
MODEL_PATH="${KATAGO_MODEL:-$KATAGO_DIR/default_model.bin.gz}"
CONFIG_PATH="${KATAGO_CONFIG:-$KATAGO_DIR/default_gtp.cfg}"
MODEL_URL="${KATAGO_MODEL_URL:-https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz}"

log() {
  printf '%s\n' "$*"
}

find_katago() {
  if [[ -n "${KATAGO_BIN:-}" && -x "${KATAGO_BIN}" ]]; then
    printf '%s\n' "${KATAGO_BIN}"
  elif command -v katago >/dev/null 2>&1; then
    command -v katago
  elif [[ -x /usr/bin/katago ]]; then
    printf '%s\n' /usr/bin/katago
  else
    return 1
  fi
}

if ! KATAGO_BIN_PATH="$(find_katago)"; then
  cat >&2 <<'EOF'
KataGo was not found.

On Fedora install the CPU backend with:
    sudo dnf install katago

On Debian/Ubuntu:
    sudo apt install katago

Then re-run this script.
EOF
  exit 1
fi
log "Using KataGo: $KATAGO_BIN_PATH"
"$KATAGO_BIN_PATH" version | head -3

mkdir -p "$KATAGO_DIR/logs"

if [[ -f "$MODEL_PATH" ]]; then
  log "Model already present: $MODEL_PATH"
else
  log "Downloading model to $MODEL_PATH"
  tmp_model="${MODEL_PATH}.part"
  curl -L --fail --retry 3 --progress-bar -o "$tmp_model" "$MODEL_URL"
  mv "$tmp_model" "$MODEL_PATH"
fi

if [[ -f "$CONFIG_PATH" ]]; then
  log "Config already present: $CONFIG_PATH"
else
  system_config=""
  for candidate in \
    /usr/share/doc/katago/configs/gtp_example.cfg \
    /usr/share/katago/configs/gtp_example.cfg; do
    if [[ -f "$candidate" ]]; then
      system_config="$candidate"
      break
    fi
  done
  if [[ -z "$system_config" ]]; then
    echo "Could not find a packaged gtp_example.cfg to copy." >&2
    exit 1
  fi
  log "Installing config from $system_config"
  cp "$system_config" "$CONFIG_PATH"
  # Redirect KataGo's GTP logs into the user-local directory.
  sed -i "s|^logDir = .*|logDir = $KATAGO_DIR/logs|" "$CONFIG_PATH"
fi

if python3 -c 'import serial' >/dev/null 2>&1; then
  log "pyserial already installed"
else
  log "Installing pyserial for LED output"
  python3 -m pip install --user pyserial
fi

cat <<EOF

KataGo is ready.

  binary: $KATAGO_BIN_PATH
  model:  $MODEL_PATH
  config: $CONFIG_PATH

Try it with:

  cd software
  python main.py --vs-katago --visits 100

With the LED panel attached:

  python main.py --vs-katago --led-serial /dev/ttyACM0
EOF
