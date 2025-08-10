#!/usr/bin/env python3
"""
Test acceso Salvum desde GitHub Actions
"""
import os
import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_salvum_from_github():
    """Test completo desde GitHub Actions"""
    logger.info("🚀 TESTING SALVUM DESDE GITHUB ACTIONS")
    logger.info("=" * 60)
    
    # Configurar navegador para GitHub Actions
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--remote-debugging-port=9222')
    
    # User agent
    options.add_argument('--user-agent=Mozilla/5.0 (Linux; x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
    
    driver = None
    try:
        # Crear driver
        logger.info("🔧 Configurando navegador...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Verificar IP
        logger.info("🌐 Verificando IP de GitHub Actions...")
        import requests
        ip_info = requests.get('https://ipinfo.io/json', timeout=10).json()
        logger.info(f"📍 IP: {ip_info.get('ip')}")
        logger.info(f"🏙️ Ciudad: {ip_info.get('city')}")
        logger.info(f"🏢 País: {ip_info.get('country')}")
        logger.info(f"🏢 Org: {ip_info.get('org')}")
        
        # Test acceso a Salvum
        logger.info("🔗 Accediendo a Salvum...")
        driver.get("https://prescriptores.salvum.cl/login")
        time.sleep(10)
        
        # Información básica
        url = driver.current_url
        titulo = driver.title
        html_size = len(driver.page_source)
        
        logger.info(f"📍 URL: {url}")
        logger.info(f"📄 Título: {titulo}")
        logger.info(f"📊 HTML size: {html_size}")
        
        # Screenshot
        driver.save_screenshot('github_salvum_test.png')
        logger.info("📸 Screenshot guardado")
        
        # Verificar si es acceso real o bloqueado
        page_source = driver.page_source.lower()
        
        if "bbva" in titulo.lower():
            resultado = "BLOQUEADO_BBVA"
            logger.error("❌ BLOQUEADO - Redirigido a BBVA")
        elif html_size < 3000:
            resultado = "BLOQUEADO_PEQUENO"
            logger.error("❌ BLOQUEADO - Página muy pequeña")
        elif "usuario" in page_source or "contraseña" in page_source:
            resultado = "ACCESO_EXITOSO"
            logger.info("✅ ACCESO EXITOSO - Página de login real!")
            
            # Intentar login
            try:
                inputs = driver.find_elements(By.TAG_NAME, "input")
                logger.info(f"📋 Inputs encontrados: {len(inputs)}")
                
                if len(inputs) >= 2:
                    # Obtener credenciales de secrets
                    usuario = os.getenv('SALVUM_USER', 'test')
                    password = os.getenv('SALVUM_PASS', 'test')
                    
                    logger.info("🔑 Intentando login...")
                    inputs[0].clear()
                    inputs[0].send_keys(usuario)
                    inputs[1].clear()
                    inputs[1].send_keys(password)
                    
                    # Buscar botón
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    if buttons:
                        buttons[0].click()
                        time.sleep(8)
                        
                        nueva_url = driver.current_url
                        logger.info(f"📍 Nueva URL: {nueva_url}")
                        
                        if nueva_url != "https://prescriptores.salvum.cl/login":
                            resultado = "LOGIN_EXITOSO"
                            logger.info("🎉 ¡LOGIN EXITOSO DESDE GITHUB!")
                        else:
                            resultado = "LOGIN_FALLÓ"
                            logger.info("⚠️ Login falló (credenciales)")
                            
            except Exception as e:
                logger.error(f"Error en login: {e}")
        else:
            resultado = "DESCONOCIDO"
            logger.warning("❓ Estado desconocido")
        
        # Guardar resultados
        results = {
            'timestamp': datetime.now().isoformat(),
            'ip_info': ip_info,
            'url': url,
            'titulo': titulo,
            'html_size': html_size,
            'resultado': resultado,
            'github_actions': True
        }
        
        with open('test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        # Log final
        with open('github_test.log', 'w') as f:
            f.write(f"Resultado: {resultado}\n")
            f.write(f"IP: {ip_info.get('ip')}\n")
            f.write(f"País: {ip_info.get('country')}\n")
            f.write(f"Título: {titulo}\n")
        
        logger.info(f"🎯 RESULTADO FINAL: {resultado}")
        return resultado in ["ACCESO_EXITOSO", "LOGIN_EXITOSO"]
        
    except Exception as e:
        logger.error(f"❌ Error general: {e}")
        return False
        
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    success = test_salvum_from_github()
    
    if success:
        print("\n🎉 ¡GITHUB ACTIONS PUEDE ACCEDER A SALVUM!")
        print("🚀 Configuremos automatización completa")
    else:
        print("\n❌ GitHub Actions también bloqueado")
        print("💡 Necesitamos Contabo o VPS independiente")
