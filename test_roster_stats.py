#!/usr/bin/env python3
import json
from yahoo_client import YahooClient

client = YahooClient()

endpoint = "team/115869.l.6/roster/players/stats"

try:
    data = client._api_request(endpoint)
    print(json.dumps(data, indent=2)[:3000])
except Exception as e:
    print(f"Error: {e}")

    # Try alternative endpoint
    print("\nTrying alternative endpoint...")
    endpoint2 = "team/115869.l.6/roster;out=stats"
    try:
        data2 = client._api_request(endpoint2)
        print(json.dumps(data2, indent=2)[:3000])
    except Exception as e2:
        print(f"Also failed: {e2}")
