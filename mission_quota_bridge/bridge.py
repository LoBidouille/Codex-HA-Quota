"""Collect Codex quotas and send only the dashboard fields to MQTT."""

import argparse
import asyncio
import json
import re
import signal
import sys
import threading
import time
import tomllib

from codex_client import CodexError, LoginRequired, read_limits
from quota import buckets, demo_snapshot, snapshot

DEFAULT_PROFILES = [{"key": "codex", "limit_id": "codex", "title": "Codex"}]


def discovery_messages(profiles, topic, expire):
    device = {"identifiers": ["mission_quota"], "name": "Mission Quota", "model": "Pont MQTT"}
    for profile in profiles:
        key, title = profile["key"], profile["title"]
        for window, label in (("short", "Court"), ("week", "Hebdo")):
            for field, name in (("remaining", "restant"), ("reset_at", "recharge")):
                unique_id = f"mission_quota_{key}_{window}_{field}"
                value = f"pages[0].{window}.{field}"
                transform = "" if field == "remaining" else ".isoformat()"
                expression = value if not transform else f"as_datetime({value}){transform}"
                config = {
                    "device": device, "name": f"{title} {label} {name}", "unique_id": unique_id,
                    "default_entity_id": f"sensor.{unique_id}",
                    "availability_topic": f"{topic}/availability",
                    "availability_template": "{{ 'online' if value == 'online' else 'offline' }}",
                    "state_topic": f"{topic}/ha_state", "expire_after": expire,
                    "value_template": (
                        "{% set pages = value_json.pages | selectattr('key', 'eq', '"
                        + key + "') | list %}"
                        + "{{ " + expression + " if pages and " + f"pages[0].{window}"
                        + " and " + value + " is not none else none }}"
                    ),
                }
                if field == "remaining":
                    config.update(unit_of_measurement="%", suggested_display_precision=0)
                else:
                    config["device_class"] = "timestamp"
                yield f"homeassistant/sensor/{unique_id}/config", config


def run(config, demo, *, stop=None, wake=None, get_limits=None, report=None):
    import paho.mqtt.client as mqtt

    options = config["mqtt"]
    topic = options.get("topic", "mission_quota")
    interval = int(config.get("poll_seconds", 300))
    if interval < 60:
        raise ValueError("poll_seconds doit valoir au moins 60")
    expiry = 2 * interval + 60
    profiles = config.get("profiles", DEFAULT_PROFILES)
    if not 1 <= len(profiles) <= 3 or len({profile["key"] for profile in profiles}) != len(profiles):
        raise ValueError("attendu : 1 à 3 profils avec des clés distinctes")
    for profile in profiles:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", profile["key"]):
            raise ValueError("clé de profil invalide")
        if not profile["limit_id"] or not 1 <= len(profile["title"].encode()) <= 32:
            raise ValueError("chaque profil doit avoir un identifiant et un titre court")

    if stop is None:
        stop = threading.Event()
        for name in (signal.SIGTERM, signal.SIGINT):
            signal.signal(name, lambda *_args: stop.set())

    def update(**state):
        if report is not None:
            report(**state)

    connected = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=options.get("client_id", "mission-quota-bridge"))

    def on_connect(_client, _userdata, _flags, reason, _properties):
        if reason.is_failure:
            update(mqtt="offline")
        else:
            connected.set()
            update(mqtt="online")

    def on_disconnect(_client, _userdata, _flags, _reason, _properties):
        connected.clear()
        update(mqtt="offline")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.will_set(f"{topic}/availability", "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    if options.get("username"):
        client.username_pw_set(options["username"], options.get("password"))
    if options.get("tls"):
        client.tls_set(ca_certs=options.get("ca_certs"))
    client.connect_async(options["host"], int(options.get("port", 1883)), keepalive=30)

    def publish(path, data, retain=False):
        payload = data if isinstance(data, str) else json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        sent = client.publish(path, payload, qos=1, retain=retain)
        sent.wait_for_publish(timeout=5)
        if not sent.is_published():
            raise ConnectionError("publication MQTT non confirmée")

    client.loop_start()
    print("Collecteur démarré" + (" en mode DÉMO" if demo else ""), flush=True)
    start = int(time.time())
    failures = 0
    waiting = False
    try:
        while not stop.is_set():
            if not connected.wait(timeout=5):
                if not waiting:
                    print("En attente du courtier MQTT", file=sys.stderr, flush=True)
                    update(mqtt="offline")
                    waiting = True
                continue
            waiting = False
            if wake is not None:
                wake.clear()
            phase = "source"
            try:
                if demo:
                    data = demo_snapshot(int(time.time()), expiry, start=start)
                else:
                    result = (get_limits() if get_limits is not None else
                              asyncio.run(read_limits(config.get("codex_binary", "codex"))))
                    data = snapshot(result, profiles, int(time.time()), expiry)
                update(source="ok", observed_at=data["observed_at"], stale_after=expiry)
                phase = "mqtt"
                if not demo:
                    for path, discovery in discovery_messages(profiles, topic, expiry):
                        publish(path, discovery, retain=True)
                publish(f"{topic}/state", data, retain=True)
                publish(f"{topic}/availability", "demo" if demo else "online", retain=True)
                if not demo:
                    publish(f"{topic}/ha_state", data)
                failures = 0
                update(mqtt="online", published_at=data["observed_at"])
                print("Relevé publié" + (" (démo)" if demo else ""), flush=True)
            except (CodexError, OSError, TimeoutError, RuntimeError) as error:
                failures += 1
                if phase == "source":
                    update(source="login_required" if isinstance(error, LoginRequired) else "error")
                else:
                    update(mqtt="offline")
                print(f"Relevé indisponible ({type(error).__name__})", file=sys.stderr, flush=True)
                if connected.is_set():
                    try:
                        publish(f"{topic}/availability", "offline", retain=True)
                    except (OSError, RuntimeError, ValueError):
                        pass
            delay = interval if not failures else min(interval, 60 * 2 ** min(failures - 1, 4))
            if not stop.is_set():
                (wake if wake is not None else stop).wait(delay)
    finally:
        if connected.is_set():
            try:
                publish(f"{topic}/availability", "offline", retain=True)
            except (OSError, RuntimeError, ValueError):
                pass
        client.disconnect()
        client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--codex-binary", default="codex", help="Chemin du binaire pour --probe")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sample", action="store_true", help="Affiche un exemple JSON sans MQTT")
    mode.add_argument("--probe", action="store_true", help="Lit les compteurs réels sans MQTT")
    mode.add_argument("--demo", action="store_true", help="Publie des données fictives sur MQTT")
    args = parser.parse_args()
    try:
        now = int(time.time())
        if args.sample:
            print(json.dumps(demo_snapshot(now, 660), ensure_ascii=False, indent=2))
        elif args.probe:
            result = asyncio.run(read_limits(args.codex_binary))
            profiles = [{"key": key, "limit_id": key, "title": key} for key in buckets(result)]
            print(json.dumps(snapshot(result, profiles, now, 660), ensure_ascii=False, indent=2))
        else:
            with open(args.config, "rb") as file:
                run(tomllib.load(file), args.demo)
    except (CodexError, OSError, TimeoutError, ValueError, KeyError) as error:
        print(f"Mission Quota · {error or type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
