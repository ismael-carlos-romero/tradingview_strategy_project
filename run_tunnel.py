import os
import sys
import json
import time
import subprocess
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DB_NAME = "trading_laboratory.db"

# Cargar configuraciones de Telegram
TELEGRAM_ENABLED = False
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            tg_conf = config.get("telegram", {})
            TELEGRAM_ENABLED = tg_conf.get("enabled", False)
            TELEGRAM_TOKEN = tg_conf.get("bot_token", "")
            TELEGRAM_CHAT_ID = tg_conf.get("chat_id", "")
    except Exception as e:
        print(f"[Tunnel Manager] Error al cargar config.json: {e}")

def send_telegram_message(message):
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Link] Telegram no configurado o deshabilitado.")
        return
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, verify=False, timeout=10)
        if r.status_code == 200:
            print("[Telegram Link] Notificación de nueva URL enviada con éxito.")
        else:
            print(f"[Telegram Link] Error al notificar ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"[Telegram Link] Excepción al notificar: {e}")

def run_ssh_tunnel():
    # Comando SSH robusto para Serveo
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-R", "80:127.0.0.1:8055",
        "serveo.net"
    ]
    
    print(f"[Tunnel Manager] Iniciando túnel SSH a serveo.net...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    
    url_detected = False
    
    # Leer la salida en tiempo real
    while True:
        line = proc.stdout.readline()
        if not line:
            break
            
        line_clean = line.strip()
        print(f"[SSH Out] {line_clean}")
        
        # Buscar la URL de reenvío
        if "Forwarding HTTP traffic from" in line_clean:
            parts = line_clean.split("from")
            if len(parts) > 1:
                url = parts[1].strip()
                print(f"[Tunnel Manager] ¡TÚNEL DETECTADO! URL pública: {url}")
                
                # Escribir a archivo local
                with open("tunnel_url.txt", "w", encoding="utf-8") as f_url:
                    f_url.write(url)
                
                # Notificar al usuario por Telegram
                msg = (
                    f"🌐 <b>Meliora Options - Laboratorio Central</b>\n"
                    f"Tu túnel de acceso remoto se ha conectado o reiniciado con éxito.\n\n"
                    f"👉 <b>Enlace de Acceso:</b>\n"
                    f"{url}\n\n"
                    f"🔑 <i>Contraseña: meliora2026</i>"
                )
                send_telegram_message(msg)
                url_detected = True
                
        # Detectar expiración silenciosa de reenvío de puertos
        if "expired" in line_clean.lower() or "connection closed" in line_clean.lower() or "closed by" in line_clean.lower():
            print("[Tunnel Manager] ¡Expiración o desconexión remota detectada! Forzando reinicio del SSH...")
            proc.kill()
            break

    return proc.wait()

def main():
    while True:
        try:
            exit_code = run_ssh_tunnel()
            print(f"[Tunnel Manager] Proceso SSH cerrado con código: {exit_code}. Reconectando en 5 segundos...")
        except Exception as e:
            print(f"[Tunnel Manager] Error general en el túnel: {e}. Reconectando en 5 segundos...")
        time.sleep(5)

if __name__ == "__main__":
    main()
