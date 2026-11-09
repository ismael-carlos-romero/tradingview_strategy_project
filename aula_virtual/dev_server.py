"""Servidor de PRUEBA del Aula Virtual (no toca el bot ni live_scanner). Sirve index.html, /assets y /api/aula/* en el puerto 8056.
Uso: python -m aula_virtual.dev_server [puerto]"""
import os, sys, json, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from aula_virtual import api

TIPOS = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".html": "text/html; charset=utf-8"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _estatico(self, rel):
        fp = os.path.normpath(os.path.join(RAIZ, rel))
        if not fp.startswith(RAIZ) or not os.path.isfile(fp):
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", TIPOS.get(os.path.splitext(fp)[1].lower(), "application/octet-stream")); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(open(fp, "rb").read())

    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/aula/"):
            return api.manejar(self, "GET")
        if p in ("/", "/index.html"):
            return self._estatico("index.html")
        if p.startswith("/assets/"):
            return self._estatico(p.lstrip("/"))
        self.send_response(404); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b"{}")

    def do_POST(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/aula/"):
            return api.manejar(self, "POST")
        if p == "/api/auth/login":
            n = int(self.headers.get("Content-Length", 0)); self.rfile.read(n)
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps({"status": "success", "session_token": "dev"}).encode()); return
        self.send_response(404); self.end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8056
    print("Aula Virtual (prueba) en http://127.0.0.1:%d" % port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
