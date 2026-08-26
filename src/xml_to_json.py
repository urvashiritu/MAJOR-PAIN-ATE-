#!/usr/bin/env python3
"""Convert Windows Security Event XML to JSON Lines for DuckDB ingestion."""

import xml.etree.ElementTree as ET
import json
import sys
from pathlib import Path

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


def parse_event(event_elem):
    system = event_elem.find("e:System", NS)
    event_data = event_elem.find("e:EventData", NS)

    record = {
        "EventID": int(system.findtext("e:EventID", "0", NS)),
        "TimeCreated": system.find("e:TimeCreated", NS).get("SystemTime", ""),
        "Computer": system.findtext("e:Computer", "", NS),
        "EventRecordID": int(system.findtext("e:EventRecordID", "0", NS)),
        "Channel": system.findtext("e:Channel", "", NS),
        "Provider": system.find("e:Provider", NS).get("Name", ""),
    }

    if event_data is not None:
        for data in event_data.findall("e:Data", NS):
            name = data.get("Name", "")
            value = data.text or ""
            record[name] = value

    return record


def main():
    xml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/windows_security_events.xml")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/windows_security_events.json")

    print(f"Parsing {xml_path} ...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    events = root.findall("e:Event", NS)
    print(f"Found {len(events)} events")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for i, event in enumerate(events):
            record = parse_event(event)
            f.write(json.dumps(record) + "\n")
            if (i + 1) % 10000 == 0:
                print(f"  {i + 1}/{len(events)} ...")

    print(f"Done → {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
