import requests
import time
import os

# La URL completa, incluido el endpoint, se obtiene de la variable de entorno
# definida en docker-compose.yml. El valor por defecto es para pruebas locales.
API_URL = os.getenv("API_URL", "http://localhost:8000/trade/execute") 

def run_scheduler():
    print("--- Scheduler iniciado. Buscando oportunidades de trading... ---")
    while True:
        try:
            print(f"\n[{time.strftime('%H:%M:%S')}] Pidiendo análisis y ejecución en: {API_URL}")
            
            # Hacer la llamada HTTP a la API (ya no se necesita el símbolo)
            response = requests.get(API_URL, timeout=30)
            response.raise_for_status() # Lanza un error para códigos 4xx/5xx

            result = response.json()
            
            # Imprimir el resultado
            if 'data' in result and 'decision' in result['data']:
                print(f"Decisión: {result['data']['decision']}")
            if 'status' in result:
                print(f"Estatus: {result['status']}")

        except requests.exceptions.RequestException as e:
            print(f"Error al llamar a la API: {e}")
            
        except Exception as e:
            print(f"Ocurrió un error inesperado: {e}")

        # Esperar 60 segundos (ajusta esto si quieres más o menos frecuencia)
        time.sleep(60) 

if __name__ == "__main__":
    run_scheduler()