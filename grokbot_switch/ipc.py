import socket
import json
import threading
import uuid
import time
from pathlib import Path
from typing import Callable, Dict, Optional

DEFAULT_PORT = 47281
HOST = "127.0.0.1"


def _json_line(sock: socket.socket, timeout: float) -> Optional[dict]:
    sock.settimeout(timeout)
    data = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in chunk:
                break
        except socket.timeout:
            raise
    if not data:
        return None
    line, _, _ = data.partition(b"\n")
    return json.loads(line.decode("utf-8"))


class IpcServer:
    def __init__(
        self,
        handler: Callable[[dict], dict],
        host: str = HOST,
        port: int = DEFAULT_PORT,
        appdata_dir: Optional[Path] = None,
    ):
        self.handler = handler
        self.host = host
        self.port = port
        self.appdata_dir = Path(appdata_dir) if appdata_dir else None
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._threads: list[threading.Thread] = []

    def start(self) -> int:
        # bind to a free port in range [port, port+20]
        for p in range(self.port, self.port + 21):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.host, p))
                s.listen()
                self._sock = s
                self.port = p
                break
            except OSError:
                continue
        else:
            raise OSError("No free port found for IPC server")

        # accept thread
        t_accept = threading.Thread(target=self._accept_loop, daemon=True)
        t_accept.start()
        self._threads.append(t_accept)

        # file watcher thread
        if self.appdata_dir:
            inbox = self.appdata_dir / "ipc_inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            t_file = threading.Thread(target=self._file_watcher, args=(inbox,), daemon=True)
            t_file.start()
            self._threads.append(t_file)

        return self.port

    def stop(self):
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        for t in self._threads:
            t.join(timeout=1.0)

    def _accept_loop(self):
        while not self._stop_event.is_set():
            try:
                self._sock.settimeout(0.5)
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            t.start()

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                request = _json_line(conn, timeout=10.0)
                if not isinstance(request, dict):
                    raise ValueError("Invalid request")
                response = self.handler(request)
                if not isinstance(response, dict):
                    raise ValueError("Handler must return dict")
                payload = json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
                conn.sendall(payload)
            except Exception as exc:
                err_resp = {"ok": False, "result": "error", "reason": str(exc)}
                try:
                    conn.sendall(json.dumps(err_resp).encode("utf-8") + b"\n")
                except OSError:
                    pass

    def _file_watcher(self, inbox: Path):
        processed: set[Path] = set()
        while not self._stop_event.is_set():
            for req_path in inbox.glob("*.json"):
                # Path.suffix of foo.response.json is ".json", not ".response.json"
                if req_path.name.endswith(".response.json") or req_path in processed:
                    continue
                try:
                    with req_path.open("r", encoding="utf-8") as f:
                        request = json.load(f)
                    response = self.handler(request)
                    resp_path = req_path.with_name(req_path.stem + ".response.json")
                    with resp_path.open("w", encoding="utf-8") as f:
                        json.dump(response, f, ensure_ascii=False)
                    req_path.unlink(missing_ok=True)
                    processed.add(req_path)
                except Exception:
                    # swallow errors; they will be retried on next loop
                    continue
            time.sleep(0.4)


def send_request(
    request: dict,
    port: int = DEFAULT_PORT,
    host: str = HOST,
    timeout: float = 15.0,
) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
        sock.sendall(payload)
        resp = _json_line(sock, timeout=timeout)
        if not isinstance(resp, dict):
            raise ValueError("Invalid response")
        return resp


def send_request_file(request: dict, appdata_dir: Path, timeout: float = 15.0) -> dict:
    inbox = Path(appdata_dir) / "ipc_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex
    req_path = inbox / f"{uid}.json"
    resp_path = inbox / f"{uid}.response.json"

    with req_path.open("w", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if resp_path.is_file():
            try:
                with resp_path.open("r", encoding="utf-8") as f:
                    response = json.load(f)
                return response
            finally:
                req_path.unlink(missing_ok=True)
                resp_path.unlink(missing_ok=True)
        time.sleep(0.2)

    # timeout cleanup
    req_path.unlink(missing_ok=True)
    resp_path.unlink(missing_ok=True)
    raise TimeoutError("IPC file request timed out")


def request_with_fallback(
    request: dict,
    port: int,
    appdata_dir: Optional[Path] = None,
    timeout: float = 15.0,
) -> dict:
    try:
        return send_request(request, port=port, timeout=timeout)
    except (ConnectionRefusedError, OSError) as exc:
        # TimeoutError is a subclass of OSError; do not fall back on a timeout.
        if isinstance(exc, TimeoutError):
            raise
        if appdata_dir:
            return send_request_file(request, Path(appdata_dir), timeout=timeout)
        raise exc
