#!/bin/bash
# Setup Celery service for EC2

set -e

echo "Setting up Celery service..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Service file path
SERVICE_FILE="/etc/systemd/system/celery.service"

# Check if service file exists
if [ -f "$SERVICE_FILE" ]; then
    echo "Celery service file already exists. Removing old one..."
    sudo systemctl stop celery 2>/dev/null || true
    sudo systemctl disable celery 2>/dev/null || true
    sudo rm "$SERVICE_FILE"
fi

# Copy service file (adjust paths based on your actual setup)
sudo cp "$SCRIPT_DIR/celery.service" "$SERVICE_FILE"

# Update paths in service file (adjust these based on your actual paths)
# Default assumes: /home/ubuntu/apps/good-bingo/arif_bingo/backend
# Update these if your paths are different
PROJECT_PATH="/home/ubuntu/apps/good-bingo/arif_bingo"
VENV_PATH="/home/ubuntu/apps/good-bingo/venv"

# Verify paths exist
if [ ! -d "$PROJECT_PATH/backend" ]; then
    echo "ERROR: Project path not found: $PROJECT_PATH/backend"
    echo "Please update paths in $SERVICE_FILE manually"
    exit 1
fi

if [ ! -d "$VENV_PATH" ]; then
    echo "ERROR: Virtual environment not found: $VENV_PATH"
    echo "Please update paths in $SERVICE_FILE manually"
    exit 1
fi

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable celery

# Start service
sudo systemctl start celery

# Check status
echo ""
echo "Celery service status:"
sudo systemctl status celery --no-pager -l

echo ""
echo "✅ Celery service setup complete!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status celery    # Check status"
echo "  sudo systemctl restart celery   # Restart service"
echo "  sudo systemctl stop celery      # Stop service"
echo "  sudo journalctl -u celery -f    # View logs (live)"
echo "  sudo journalctl -u celery -n 100 # View last 100 log lines"

