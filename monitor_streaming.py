#!/usr/bin/env python3
"""Monitor ProPresenter streaming endpoint for timer updates."""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

async def monitor_streaming():
    """Monitor the streaming endpoint."""
    url = "http://192.168.1.167:51482/v1/status/updates"
    endpoints = ["timers", "timers/current"]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to streaming endpoint...")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring: {endpoints}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for updates...\n")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=endpoints,
                headers={'Content-Type': 'application/json'}
            ) as response:
                response.raise_for_status()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Connected! Reading stream...\n")
                
                # Read the chunked response line by line
                async for line in response.content:
                    if line:
                        try:
                            decoded_line = line.decode('utf-8').strip()
                            if decoded_line:
                                data = json.loads(decoded_line)
                                path = data.get('url', 'unknown')
                                update_data = data.get('data')
                                
                                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                                
                                # Only show timer-related updates
                                if 'timer' in path.lower():
                                    print(f"\n{'='*80}")
                                    print(f"[{timestamp}] PATH: {path}")
                                    print(f"{'='*80}")
                                    
                                    if isinstance(update_data, list):
                                        print(f"DATA (array with {len(update_data)} items):")
                                        for i, item in enumerate(update_data):
                                            print(f"\n  [{i}] {json.dumps(item, indent=4)}")
                                    elif isinstance(update_data, dict):
                                        print(f"DATA (object):")
                                        print(json.dumps(update_data, indent=2))
                                    else:
                                        print(f"DATA: {update_data}")
                                    print(f"{'='*80}\n")
                                    
                        except json.JSONDecodeError as err:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ JSON decode error: {err}")
                        except Exception as err:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Error: {err}")
                            
    except aiohttp.ClientConnectorError as err:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Cannot connect: {err}")
    except aiohttp.ClientError as err:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Connection error: {err}")
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Stopped by user")
    except Exception as err:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Unexpected error: {err}")

if __name__ == "__main__":
    print("\n" + "="*80)
    print("ProPresenter Timer Streaming Monitor")
    print("="*80 + "\n")
    print("Instructions:")
    print("1. This script will show all timer-related streaming updates")
    print("2. Change a timer's duration or name in ProPresenter")
    print("3. Watch for 'timers' or 'timers/current' updates below")
    print("4. Press Ctrl+C to stop\n")
    
    asyncio.run(monitor_streaming())
