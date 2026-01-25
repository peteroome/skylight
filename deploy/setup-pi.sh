#!/bin/bash
# deploy/setup-pi.sh - First-time Raspberry Pi setup for Skylight

set -e

echo "Setting up Skylight on Raspberry Pi..."

# Install dependencies
echo "Installing dependencies..."
sudo apt update
sudo apt install -y python3 python3-requests surf unclutter xdotool

# Increase GPU memory for better graphics performance
if ! grep -q "gpu_mem=128" /boot/firmware/config.txt 2>/dev/null; then
  echo "gpu_mem=128" | sudo tee -a /boot/firmware/config.txt
fi

# Disable screensaver - remove xscreensaver entirely
echo "Disabling screensaver..."
sudo apt remove -y xscreensaver xscreensaver-data xscreensaver-data-extra 2>/dev/null || true
sudo rm -f /etc/xdg/autostart/xscreensaver.desktop
rm -f ~/.config/autostart/xscreensaver.desktop

# Disable screen blanking via lightdm (if present)
if [ -d /etc/lightdm/lightdm.conf.d ]; then
  sudo tee /etc/lightdm/lightdm.conf.d/10-blanking.conf > /dev/null <<EOF
[SeatDefaults]
xserver-command=X -s 0 -dpms
EOF
fi

# Hide mouse cursor automatically
mkdir -p ~/.config/lxsession/LXDE-pi
echo "@unclutter -idle 0" >> ~/.config/lxsession/LXDE-pi/autostart 2>/dev/null || true

# Create web server service
echo "Creating HTTP server service..."
sudo tee /etc/systemd/system/skylight-http.service > /dev/null <<EOF
[Unit]
Description=Skylight HTTP server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/skylight/web
ExecStart=/usr/bin/python3 -m http.server 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Copy service files
echo "Installing systemd services..."
sudo cp /home/pi/skylight/deploy/skylight-data.service /etc/systemd/system/
sudo cp /home/pi/skylight/deploy/skylight-display.service /etc/systemd/system/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable skylight-http
sudo systemctl enable skylight-data
sudo systemctl enable skylight-display

# Start services
sudo systemctl start skylight-http
sudo systemctl start skylight-data
sudo systemctl start skylight-display

echo ""
echo "Skylight installed!"
echo "   Services will start automatically on boot."
echo ""
echo "   Useful commands:"
echo "   - sudo systemctl status skylight-data"
echo "   - sudo systemctl restart skylight-display"
echo "   - journalctl -u skylight-data -f"
