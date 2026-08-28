import os
import time
import sys
from PIL import ImageGrab

def main():
    # Asegurar codificación utf-8 para caracteres unicode en terminales Windows
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("=================================================================")
    print("      📸 CAPTURADOR DE PANTALLA EN VIVO PARA PORTAL GEMINI 📸     ")
    print("=================================================================")
    print("Este script captura tu pantalla completa cada 5 segundos")
    print("y la guarda como 'live_view.png' en esta carpeta del proyecto.")
    print("De este modo, Gemini podrá 'ver' tu pantalla para diagnosticar y")
    print("ayudarte con el sincronizador o cualquier problema visual.")
    print("\n[INFO] Para detener el script, presiona CTRL+C en esta terminal.")
    print("=================================================================\n")

    output_filename = "live_view.png"
    
    # Obtener ruta absoluta de la carpeta de trabajo
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_dir, output_filename)

    try:
        while True:
            # Capturar pantalla completa
            screenshot = ImageGrab.grab()
            # Guardar sobrescribiendo la anterior
            screenshot.save(output_path)
            
            # Imprimir confirmación con hora local
            timestamp = time.strftime('%H:%M:%S')
            print(f"[{timestamp}] 👁️ Pantalla capturada. Imagen lista en: {output_filename}", end="\r")
            
            # Esperar 5 segundos
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Capturador automático detenido por el usuario.")
    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
        print("Asegúrate de ejecutar el script en una terminal y que no esté bloqueado el acceso a la pantalla.")

if __name__ == "__main__":
    main()
