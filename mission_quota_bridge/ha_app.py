"""Run Mission Quota as a Home Assistant OS app."""

import asyncio
import hmac
import json
import logging
import re
import secrets
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from aiohttp import ClientError, web

from bridge import DEFAULT_PROFILES, run
from codex_client import AppServer, CodexError, LoginRequired
from ha_config import Settings
from quota import snapshot

LOG = logging.getLogger("mission-quota")
DEVICE_URL = "https://auth.openai.com/codex/device"
SUPERVISOR_IP = "172.30.32.2"
SOURCE_ERRORS = (CodexError, OSError, TimeoutError)


@dataclass(frozen=True)
class Login:
    owner: str
    id: str
    code: str
    deadline: int


class Mission:
    def __init__(self, settings, web_root, *, binary="codex", login_timeout=900):
        self.settings = settings
        self.web_root = web_root
        self.env = settings.codex_env()
        self.binary = binary
        self.login_timeout = login_timeout
        self.rpc = None
        self.rpc_lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        self.login = None
        self.login_timer = None
        self.notifications = set()
        self.auth = "checking"
        self.login_result = None
        self.source = "waiting"
        self.mqtt = "waiting" if settings.publish else "disabled"
        self.last_read = self._load_timestamp()
        self.last_publication = None
        self.page = None
        self.stale_after = 2 * settings.interval + 60
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.probe_lock = asyncio.Lock()
        self.closing = False

    def _load_timestamp(self):
        try:
            stamp = int((self.settings.data / "last-relevant.txt").read_text())
            return stamp if 0 < stamp <= time.time() else None
        except (ValueError, OSError):
            return None

    def report(self, *, source=None, observed_at=None, mqtt=None, published_at=None, **_unused):
        if source:
            self.source = source
        if mqtt:
            self.mqtt = mqtt
        if published_at:
            self.last_publication = published_at
        if observed_at and observed_at != self.last_read:
            self.last_read = observed_at
            try:
                final = self.settings.data / "last-relevant.txt"
                temporary = final.with_suffix(".tmp")
                temporary.write_text(str(observed_at))
                temporary.replace(final)
            except OSError:
                LOG.warning("Impossible de conserver l’heure du relevé")

    async def connection(self):
        async with self.rpc_lock:
            if self.closing:
                raise CodexError("Arrêt en cours")
            if self.rpc is None or not self.rpc.running:
                if self.rpc is not None:
                    await self.rpc.close()
                self.rpc = await AppServer(self.binary, env=self.env, on_notification=self.notify).__aenter__()
            return self.rpc

    def notify(self, message):
        if message.get("method") != "account/login/completed":
            return
        task = asyncio.create_task(self.complete_login(message.get("params")))
        self.notifications.add(task)
        task.add_done_callback(self.notifications.discard)

    async def complete_login(self, params):
        if not isinstance(params, dict):
            return
        async with self.login_lock:
            if self.login is None or params.get("loginId") != self.login.id:
                return
            error = params.get("error")
            expired = isinstance(error, str) and "expir" in error.lower()
            self.clear_login("connected" if params.get("success") is True else "expired" if expired else "failed")
        await self.check_account()
        if self.auth == "connected":
            self.wake.set()

    def clear_login(self, result):
        if self.login_timer is not None and self.login_timer is not asyncio.current_task():
            self.login_timer.cancel()
        self.login = self.login_timer = None
        self.login_result = result

    async def check_account(self):
        try:
            rpc = await self.connection()
            result = await rpc.request("account/read", {"refreshToken": False})
            if not isinstance(result, dict) or "account" not in result:
                raise CodexError("État du compte indisponible")
        except SOURCE_ERRORS:
            self.auth = "unknown"
            return
        account = result["account"]
        self.auth = "connected" if isinstance(account, dict) and account.get("type") == "chatgpt" else "required"

    async def start_login(self, user):
        async with self.login_lock:
            if self.login:
                return "busy" if self.login.owner != user else None
            try:
                rpc = await self.connection()
                data = await rpc.request("account/login/start", {"type": "chatgptDeviceCode"})
                login_id = data.get("loginId") if isinstance(data, dict) else None
                if not isinstance(login_id, str) or not login_id:
                    self.login_result = "failed"
                    return "failed"
                code = data.get("userCode")
                if (data.get("type") != "chatgptDeviceCode" or data.get("verificationUrl") != DEVICE_URL
                        or not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9-]{4,24}", code)):
                    with suppress(*SOURCE_ERRORS):
                        await rpc.request("account/login/cancel", {"loginId": login_id}, timeout=5)
                    self.login_result = "failed"
                    return "failed"
            except SOURCE_ERRORS:
                self.login_result = "failed"
                return "failed"
            self.login_result = None
            self.login = Login(user, login_id, code, int(time.time()) + self.login_timeout)
            self.login_timer = asyncio.create_task(self.expire(self.login))
            return None

    async def expire(self, login):
        await asyncio.sleep(self.login_timeout)
        async with self.login_lock:
            if self.login is login:
                await self.cancel_login_locked("expired")

    async def cancel_login_locked(self, result):
        if self.rpc and self.rpc.running:
            with suppress(*SOURCE_ERRORS):
                await self.rpc.request("account/login/cancel", {"loginId": self.login.id}, timeout=5)
        self.clear_login(result)

    async def cancel_login(self, user):
        async with self.login_lock:
            if self.login and self.login.owner != user:
                return "busy"
            if self.login:
                await self.cancel_login_locked("cancelled")
            return None

    async def read_live(self):
        async with self.probe_lock:
            if self.auth != "connected":
                await self.check_account()
            if self.auth == "required":
                raise LoginRequired("Connexion à ChatGPT requise")
            if self.auth != "connected":
                raise CodexError("Compte ChatGPT indisponible")
            try:
                data = await (await self.connection()).rate_limits()
            except CodexError as error:
                detail = error.detail.lower()
                if error.code == 401 or re.search(r"\b401\b|unauthorized|not logged in|authentication required", detail):
                    self.auth = "required"
                    raise LoginRequired("Connexion à ChatGPT requise") from None
                raise
            now = int(time.time())
            self.page = snapshot(data, DEFAULT_PROFILES, now, self.stale_after)["pages"][0]
            self.report(source="ok", observed_at=now)
            return data

    async def probe(self):
        try:
            await self.read_live()
        except LoginRequired:
            self.report(source="login_required")
        except SOURCE_ERRORS:
            self.report(source="error")

    async def collect(self):
        loop = asyncio.get_running_loop()

        def read():
            future = asyncio.run_coroutine_threadsafe(self.read_live(), loop)
            try:
                return future.result(timeout=60)
            except TimeoutError:
                future.cancel()
                raise

        def report(**updates):
            loop.call_soon_threadsafe(lambda: self.report(**updates))

        while not self.closing:
            try:
                mqtt = await self.settings.mqtt()
                await asyncio.to_thread(
                    run, {"poll_seconds": self.settings.interval, "mqtt": mqtt}, False,
                    stop=self.stop, wake=self.wake, get_limits=read, report=report,
                )
            except (OSError, ClientError, ValueError, TypeError, KeyError):
                self.report(mqtt="offline")
                LOG.warning("Courtier MQTT indisponible")
                await asyncio.sleep(30)

    async def lifecycle(self, _app):
        initial = asyncio.create_task(self.check_account())
        worker = asyncio.create_task(self.collect()) if self.settings.publish else None
        try:
            yield
        finally:
            self.closing = True
            self.stop.set()
            self.wake.set()
            if self.login_timer:
                self.login_timer.cancel()
            initial.cancel()
            await asyncio.gather(initial, *self.notifications, return_exceptions=True)
            async with self.rpc_lock:
                if self.rpc:
                    await self.rpc.close()
            # A pending broker discovery can be cancelled. A running thread gets the stop event.
            if worker:
                try:
                    await asyncio.wait_for(worker, timeout=12)
                except TimeoutError:
                    LOG.warning("Fin du collecteur MQTT après délai")

    def state(self, user):
        device = None
        if self.login and self.login.owner == user:
            device = {"url": DEVICE_URL, "code": self.login.code, "deadline": self.login.deadline}
        return {
            "auth": self.auth, "login": self.login_result, "busy": self.login is not None,
            "device": device, "source": self.source, "mqtt": self.mqtt,
            "observed_at": self.last_read, "published_at": self.last_publication,
            "stale": bool(self.last_read and (self.source in {"error", "login_required"}
                                             or time.time() - self.last_read > self.stale_after)),
            "page": self.page,
        }


def app_for(mission, *, proxy_ip=SUPERVISOR_IP):
    secret = secrets.token_bytes(32)

    def nonce(user):
        return hmac.digest(secret, user.encode(), "sha256").hex()

    @web.middleware
    async def ingress(request, handler):
        user = request.headers.get("X-Remote-User-Id")
        if request.remote != proxy_ip or not user:
            raise web.HTTPForbidden()
        if request.method == "POST" and not hmac.compare_digest(
                request.headers.get("X-Mission-CSRF", "").encode(), nonce(user).encode()):
            raise web.HTTPForbidden()
        request["user"] = user
        return await handler(request)

    async def headers(_request, response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        )

    async def dashboard(_request):
        return web.FileResponse(mission.web_root / "index.html")

    async def asset(request):
        return web.FileResponse(mission.web_root / request.match_info["file"])

    def state(request):
        user = request["user"]
        return mission.state(user) | {"csrf": nonce(user)}

    async def get_state(request):
        return web.json_response(state(request))

    async def action(request):
        user = request["user"]
        name = request.match_info["action"]
        error = None
        if name == "connect":
            error = await mission.start_login(user)
        elif name == "cancel":
            error = await mission.cancel_login(user)
        elif not mission.probe_lock.locked():
            await mission.probe()
        return web.json_response(state(request) | {"action_error": error})

    app = web.Application(middlewares=[ingress], client_max_size=1024)
    app.on_response_prepare.append(headers)
    app.cleanup_ctx.append(mission.lifecycle)
    app.router.add_get("/", dashboard)
    app.router.add_get("/{file:app.js|app.css}", asset)
    app.router.add_get("/api/state", get_state)
    app.router.add_post("/api/{action:connect|cancel|probe}", action)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    data = Path("/data")
    try:
        mission = Mission(Settings.load(data), Path(__file__).parent / "web")
    except (OSError, ValueError, TypeError, AttributeError):
        raise SystemExit("Vérifie les options de Mission Quota et le stockage local")
    web.run_app(app_for(mission), host="0.0.0.0", port=8099, access_log=None, print=None, shutdown_timeout=8)
