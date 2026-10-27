#!/bin/bash

# WiFi Sensing Data Collection Script
# This script automatically activates the virtual environment and runs data collection

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to the project directory
cd "$DIR"

# Activate virtual environment
source .venv/bin/activate

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Virtual environment activated: $(python --version)"
else
    echo "❌ Failed to activate virtual environment"
    exit 1
fi

# Default config file
CONFIG_FILE="config/my_config.yaml"

# Check if config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ Configuration file not found: $CONFIG_FILE"
    echo "Please run setup_test.py first to create the configuration"
    exit 1
fi

echo "📊 Starting WiFi Sensing Data Collection"
echo "Configuration: $CONFIG_FILE"
echo "Use Ctrl+C to stop data collection"
echo ""

# Run the data collection script with provided arguments, or default arguments
if [[ $# -eq 0 ]]; then
    # No arguments provided, use default
    python scripts/collect_data.py --config "$CONFIG_FILE"
else
    # Use provided arguments
    python scripts/collect_data.py "$@"
fi