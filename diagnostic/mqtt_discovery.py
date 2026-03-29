#!/usr/bin/env python3
"""
MQTT Discovery: Zeigt alle eingehenden MQTT-Topics der Station.
Sammelt und gruppiert nach Pattern, zeigt Unique Topics + Werte.
"""

import argparse
import os
import paho.mqtt.client as mqtt
import sys
import time
from collections import defaultdict
from typing import DefaultDict


def main():
    parser = argparse.ArgumentParser(
        description="Entdecke alle MQTT-Topics der WXsmart-Station.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Alle Topics 60 Sekunden lang sammeln
  %(prog)s --duration 60

  # Nur Station-Topics (schneller Überblick)
  %(prog)s --pattern "Station" --duration 30

  # Tip-Topics 90 Sekunden erfassen
  %(prog)s --pattern "Tip" --duration 90

  # Tool-Power-Topics live beobachten
  %(prog)s --pattern "Tool.*Power" --duration 45 --regex

  # Alles außer Log-Topics
  %(prog)s --exclude "LOG" --duration 60
        """,
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Wie lange lauschen in Sekunden (default: 60)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=None,
        help="Filter: nur Topics mit diesem String (case-insensitive)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="Ausschließen: Topics mit diesem String ignorieren",
    )
    parser.add_argument(
        "--regex",
        action="store_true",
        help="Pattern als Regex statt einfacher String-Match verwenden",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MQTT_HOST", "localhost"),
        help="MQTT-Host (default: localhost oder MQTT_HOST env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_PORT", "9001")),
        help="MQTT-Port (default: 9001 oder MQTT_PORT env)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        default=os.getenv("MQTT_TRANSPORT", "websockets"),
        help="MQTT-Transport (default: websockets oder MQTT_TRANSPORT env)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Zeige vollständige Werte (nicht gekürzt)",
    )
    parser.add_argument(
        "--group",
        action="store_true",
        help="Gruppiere Topics nach Prefix (Station/Tool/Tip/Config/etc.)",
    )
    args = parser.parse_args()

    topics_dict: DefaultDict[str, list[str]] = defaultdict(list)
    stats = {"total_messages": 0, "unique_topics": 0}
    stats = {"total_messages": 0, "unique_topics": 0}

    def on_connect(c: mqtt.Client, u: object, f: dict[str, int], rc: int) -> None:
        c.subscribe("WXSMART/#")

    def on_message(c: mqtt.Client, u: object, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        payload = msg.payload.decode(errors="replace")

        # Filter anwenden
        if args.exclude:
            if args.exclude.lower() in topic.lower():
                return

        if args.pattern:
            if args.regex:
                import re

                if not re.search(args.pattern, topic, re.IGNORECASE):
                    return
            else:
                if args.pattern.lower() not in topic.lower():
                    return

        # Sammeln
        if topic not in topics_dict:
            stats["unique_topics"] += 1
        topics_dict[topic].append(payload)
        stats["total_messages"] += 1

    client = mqtt.Client(transport=args.transport)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, 10)
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Starte MQTT-Discovery für {args.duration}s…")
    print(
        f"   Host: {args.host}:{args.port}  |  Transport: {args.transport}  |  Filter: {args.pattern or 'keine'}\n"
    )

    client.loop_start()
    time.sleep(args.duration)
    client.loop_stop()
    client.disconnect()

    # Ausgabe
    print(f"\n📊 Statistik:")
    print(f"   Gesamt Messages: {stats['total_messages']}")
    print(f"   Unique Topics:   {stats['unique_topics']}")

    if not topics_dict:
        print("\n⚠️  Keine Topics gefunden. Prüfe Host/Port/Filter.")
        sys.exit(0)
    if args.group:
        # Gruppierte Ausgabe
        groups: DefaultDict[str, list[str]] = defaultdict(list)
        for topic in topics_dict.keys():
            parts = topic.split("/")
            parts = topic.split("/")
            if len(parts) >= 4:
                group_key = parts[3]  # z.B. "Station1", "Tool1", "Tip1", "Config"
                groups[group_key].append(topic)
        
        print(f"\n📦 Topics nach Gruppe:\n")
        for group in sorted(groups.keys()):
            topics_in_group = groups[group]
            print(f"\n🔹 {group}  ({len(topics_in_group)} Topics)")
            print("-" * 110)
            for topic in sorted(topics_in_group):
                values = topics_dict[topic]
                count = len(values)
                last_value = values[-1]
                
                # Kurze Topicpath
                short_topic = "/".join(topic.split("/")[4:])
                
                if args.verbose:
                    print(f"  {short_topic:<50} Count: {count:>3}  Value: {last_value}")
                else:
                    display_value = last_value[:40] + "…" if len(last_value) > 40 else last_value
                    print(f"  {short_topic:<50} Count: {count:>3}  Value: {display_value}")
    else:
        # Standard-Ausgabe (flache Liste)
        print(f"\n📋 Topics (sortiert):\n")
        print(f"{'Topic':<70} {'Count':>6} {'Letzter Wert':<30}")
        print("-" * 110)

        for topic in sorted(topics_dict.keys()):
            values = topics_dict[topic]
            count = len(values)
            last_value = values[-1]
            
            if args.verbose:
                display_value = last_value
            else:
                display_value = last_value[:28] + "…" if len(last_value) > 28 else last_value
            
            print(f"{topic:<70} {count:>6} {display_value:<30}")


if __name__ == "__main__":
    main()
