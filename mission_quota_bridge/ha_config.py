"""Home Assistant options, private Codex storage and MQTT service discovery."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp


@dataclass(frozen=True)
class Settings:
    data: Path
    publish: bool = False
    interval: int = 300
    topic: str = "mission_quota"
    host: str = ""
    port: int = 1883
    username: str = ""
    password: str = ""
    tls: bool = False

    @classmethod
    def load(cls, data):
        raw = json.loads((data / "options.json").read_text())
        settings = cls(
            data, raw.get("publish_enabled", False), raw.get("poll_seconds", 300),
            raw.get("mqtt_topic", "mission_quota"), raw.get("mqtt_host", "").strip(),
            raw.get("mqtt_port", 1883), raw.get("mqtt_username", ""),
            raw.get("mqtt_password", ""), raw.get("mqtt_tls", False),
        )
        if not 60 <= settings.interval <= 3600 or not 1 <= settings.port <= 65535:
            raise ValueError("Intervalle ou port MQTT invalide")
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", settings.topic):
            raise ValueError("Préfixe MQTT invalide")
        return settings

    def codex_env(self):
        legacy = self.data / ".codex"
        home = legacy if (legacy / "auth.json").is_file() else self.data / "codex"
        home.mkdir(mode=0o700, exist_ok=True)
        home.chmod(0o700)
        config = home / "config.toml"
        if not config.exists():
            config.write_text('cli_auth_credentials_store = "file"\n', encoding="utf-8")
        env = dict(os.environ)
        for key in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY"):
            env.pop(key, None)
        env["CODEX_HOME"] = str(home)
        return env

    async def mqtt(self):
        options = {"topic": self.topic}
        if self.host:
            return options | {"host": self.host, "port": self.port, "username": self.username,
                              "password": self.password, "tls": self.tls}
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            raise ConnectionError("Service MQTT indisponible")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as client:
            async with client.get("http://supervisor/services/mqtt", allow_redirects=False,
                                  headers={"Authorization": f"Bearer {token}"}) as response:
                response.raise_for_status()
                service = (await response.json())["data"]
        if not service.get("host") or not service.get("port"):
            raise ConnectionError("Service MQTT indisponible")
        return options | {"host": service["host"], "port": service["port"],
                          "username": service.get("username"), "password": service.get("password"),
                          "tls": service.get("ssl", False)}
