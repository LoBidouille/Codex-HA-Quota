"""Local JSON-RPC transport for the documented Codex App Server."""

import asyncio
import itertools
import json


class CodexError(Exception):
    def __init__(self, message, *, code=None, detail=""):
        super().__init__(message)
        self.code = code
        self.detail = detail


class LoginRequired(CodexError):
    pass


class AppServer:
    def __init__(self, binary, *, on_notification=None, env=None):
        self.binary = binary
        self.on_notification = on_notification
        self.env = env
        self.process = None
        self.reader = None
        self.pending = {}
        self.ids = itertools.count(1)

    @property
    def running(self):
        return bool(self.process and self.process.returncode is None and self.reader and not self.reader.done())

    async def __aenter__(self):
        self.process = await asyncio.create_subprocess_exec(
            self.binary, "app-server", "--stdio", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=1024 * 1024, env=self.env,
        )
        self.reader = asyncio.create_task(self._read())
        try:
            await self.request("initialize", {"clientInfo": {"name": "mission-quota", "version": "1.1.0"}})
            await self._send({"method": "initialized", "params": {}})
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(self, *_args):
        await self.close()

    async def close(self):
        process, reader = self.process, self.reader
        if process is not None and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        if reader is not None:
            await reader
        self.process = self.reader = None

    async def _send(self, message):
        try:
            self.process.stdin.write(json.dumps(message).encode() + b"\n")
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise CodexError("connexion Codex interrompue") from error

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                reply = json.loads(line)
                if not isinstance(reply, dict):
                    raise ValueError("réponse JSON-RPC invalide")
                if reply.get("method"):
                    if "id" in reply:
                        await self._send({"id": reply["id"], "error": {
                            "code": -32601, "message": "Method not supported",
                        }})
                    elif self.on_notification:
                        self.on_notification(reply)
                    continue
                pending = self.pending.get(reply.get("id"))
                if pending is not None and not pending.done():
                    pending.set_result(reply)
        except (ValueError, TypeError, OSError, CodexError):
            # Incoming messages can carry account metadata. Expose a fixed error instead.
            pass
        finally:
            for pending in self.pending.values():
                if not pending.done():
                    pending.set_exception(CodexError("le serveur Codex a fermé la connexion"))

    async def request(self, method, params=None, *, timeout=18):
        if not self.running:
            raise CodexError("connexion Codex indisponible")
        number = next(self.ids)
        future = asyncio.get_running_loop().create_future()
        self.pending[number] = future
        message = {"id": number, "method": method}
        if params is not None:
            message["params"] = params
        try:
            async with asyncio.timeout(timeout):
                await self._send(message)
                reply = await future
        finally:
            self.pending.pop(number)
            if not future.done():
                future.cancel()
        error = reply.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            detail = error.get("message")
            raise CodexError(
                f"{method} a renvoyé le code {code if type(code) is int else 'inconnu'}",
                code=code, detail=detail if isinstance(detail, str) else "",
            )
        if "result" not in reply:
            raise CodexError("réponse Codex illisible")
        return reply["result"]

    async def rate_limits(self):
        result = await self.request("account/rateLimits/read")
        if not isinstance(result, dict) or not ({"rateLimits", "rateLimitsByLimitId"} & result.keys()):
            raise CodexError("la réponse ne contient aucun champ de quota reconnu")
        return result


async def read_limits(binary):
    async with AppServer(binary) as process:
        return await process.rate_limits()
