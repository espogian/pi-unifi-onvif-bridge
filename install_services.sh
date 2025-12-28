#!/bin/bash

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit
fi

echo "--- Starting Installation ---"

# 1. Install Node.js and NPM via apt
echo "Installing Node.js and NPM from repositories..."
apt-get update
apt-get install -y nodejs npm

# 2. Create MediaMTX Service
echo "Creating MediaMTX Service..."
cat <<EOF > /etc/systemd/system/mediamtx.service
[Unit]
Description=MediaMTX RTSP Server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/mediamtx
ExecStart=/home/pi/mediamtx/mediamtx /home/pi/mediamtx/mediamtx.yml
Restart=always
RestartSec=5
# Ottimizzazione priorità processo
Nice=-10

[Install]
WantedBy=multi-user.target
EOF

# 3. Create ONVIF Server Service
echo "Creating ONVIF Server Service..."
cat <<EOF > /etc/systemd/system/onvif-server.service
[Unit]
Description=NodeJS ONVIF Server
After=network.target mediamtx.service

[Service]
User=pi
WorkingDirectory=/home/pi/onvif-server
# Using /usr/bin/node as requested. Ensure your config file is named config.yaml
ExecStart=/usr/bin/node main.js config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 4. Enable and Start Services
echo "Reloading SystemD daemon..."
systemctl daemon-reload

echo "Enabling services on boot..."
systemctl enable mediamtx
systemctl enable onvif-server

echo "Starting services..."
systemctl start mediamtx
systemctl start onvif-server

echo "--- Setup Complete! ---"
systemctl status mediamtx --no-pager
systemctl status onvif-server --no-pager
