#!/bin/bash
# deploy/setup-pi.sh - First-time Raspberry Pi setup for Skylight

set -e

echo "Setting up Skylight on Raspberry Pi..."

# Install dependencies
echo "Installing dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip chromium-browser

# Install Python packages
pip3 install requests

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
