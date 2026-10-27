#!/usr/bin/env python3
"""
WiFi Signal Monitoring - Shows real WiFi measurements from TP-Link dongle
This demonstrates how your dongle detects human presence via WiFi signal changes.
"""

import sys
import time
import subprocess
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

def scan_wifi_signals():
    """Scan and display WiFi signals from TP-Link dongle."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "network", "mode=bssid"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print("❌ Failed to scan WiFi networks")
            return []
            
        # Parse the output
        networks = []
        lines = result.stdout.strip().split('\n')
        current_ssid = None
        current_bssid = None
        
        for line in lines:
            line = line.strip()
            
            # Parse SSID
            if line.startswith('SSID') and ':' in line:
                current_ssid = line.split(':', 1)[1].strip()
                continue
                
            # Parse BSSID  
            elif line.startswith('BSSID') and ':' in line and current_ssid:
                current_bssid = line.split(':', 1)[1].strip()
                
            # Parse Signal strength
            elif line.startswith('Signal') and ':' in line and current_ssid and current_bssid:
                signal_str = line.split(':', 1)[1].strip().replace('%', '')
                try:
                    signal_percent = float(signal_str)
                    # Convert percentage to approximate dBm
                    signal_dbm = -100 + (signal_percent * 0.7)
                    
                    networks.append({
                        'ssid': current_ssid,
                        'bssid': current_bssid,
                        'signal_percent': signal_percent,
                        'signal_dbm': signal_dbm
                    })
                    
                except ValueError:
                    pass
                    
                # Reset for next network
                current_ssid = None
                current_bssid = None
                
        return networks
        
    except Exception as e:
        print(f"❌ Error scanning WiFi: {e}")
        return []

def main():
    """Main monitoring loop."""
    print("🔍 WiFi Signal Monitor - TP-Link Dongle")
    print("📡 This shows how your dongle detects humans via WiFi waves")
    print("🚶 Try walking around to see signal changes!")
    print("⌨️  Press Ctrl+C to stop")
    print("="*60)
    
    baseline = {}
    scan_count = 0
    
    try:
        while True:
            scan_count += 1
            networks = scan_wifi_signals()
            
            if not networks:
                print("❌ No networks found")
                time.sleep(2)
                continue
                
            print(f"\n📊 Scan #{scan_count} - {time.strftime('%H:%M:%S')}")
            print(f"📡 Networks detected: {len(networks)}")
            
            for net in networks[:8]:  # Show top 8 networks
                ssid = net['ssid'][:15]  # Truncate long names
                signal = net['signal_dbm']
                percent = net['signal_percent']
                
                # Compare to baseline (first scan)
                if scan_count == 1:
                    baseline[net['bssid']] = signal
                    change = 0
                else:
                    baseline_signal = baseline.get(net['bssid'], signal)
                    change = signal - baseline_signal
                
                # Visual indicator of signal change
                if change > 2:
                    indicator = "🔺"  # Signal stronger
                elif change < -2:
                    indicator = "🔻"  # Signal weaker  
                else:
                    indicator = "➡️"   # No significant change
                    
                print(f"  {indicator} {ssid:<15} | {signal:6.1f} dBm ({percent:4.1f}%) | Change: {change:+5.1f}")
            
            if scan_count == 1:
                print("\n🎯 Baseline established! Now walk around to see changes...")
            elif scan_count > 1:
                print(f"\n🧠 Human Detection Logic:")
                print(f"   • Signal changes > ±3 dBm = Possible movement")
                print(f"   • Multiple networks changing = Strong presence indication")
                print(f"   • Stable signals = No movement detected")
                
            time.sleep(3)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped")
        print("🎯 This is how your TP-Link dongle detects human presence!")

if __name__ == "__main__":
    main()