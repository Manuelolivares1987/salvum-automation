#!/usr/bin/env python3
"""Test acceso Salvum desde GitHub Actions - VERSIÓN MEJORADA"""
import os
import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_salvum_login_mejorado():
    """Test completo mejorado desde GitHub Actions"""
    logger.info("🚀 TESTING SALVUM MEJORADO - GITHUB ACTIONS")
    logger.info("=" * 60)
    
    # Configurar navegador optimizado
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--remote-debugging-port=9222')
    
    # User agent específico
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
    
    # Optimizaciones adicionales
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        # Crear driver
        logger.info("🔧 Configurando navegador mejorado...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Configurar timeouts
        driver.set_page_load_timeout(30)
        wait = WebDriverWait(driver, 20)
        
        # Ocultar detección de automatización
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Verificar IP
        logger.info("🌐 Verificando IP de GitHub Actions...")
        import requests
        ip_info = requests.get('https://ipinfo.io/json', timeout=10).json()
        logger.info(f"📍 IP: {ip_info.get('ip')}")
        logger.info(f"🏙️ Ciudad: {ip_info.get('city')}")
        logger.info(f"🏢 País: {ip_info.get('country')}")
        logger.info(f"🏢 Org: {ip_info.get('org')}")
        
        # Acceder a Salvum
        logger.info("🔗 Accediendo a Salvum...")
        driver.get("https://prescriptores.salvum.cl/login")
        
        # Esperar carga completa
        logger.info("⏳ Esperando carga completa...")
        time.sleep(15)  # Espera más larga
        
        # Información de la página
        url = driver.current_url
        titulo = driver.title
        html_size = len(driver.page_source)
        
        logger.info(f"📍 URL: {url}")
        logger.info(f"📄 Título: {titulo}")
        logger.info(f"📊 HTML size: {html_size}")
        
        # Screenshot inicial
        driver.save_screenshot('salvum_pagina_inicial.png')
        logger.info("📸 Screenshot inicial guardado")
        
        # Verificar si llegamos a la página correcta
        page_source = driver.page_source.lower()
        
        if "bbva" in titulo.lower():
            resultado = "BLOQUEADO_BBVA"
            logger.error("❌ BLOQUEADO - Redirigido a BBVA")
            return False
        elif html_size < 5000:
            resultado = "BLOQUEADO_PEQUENO"
            logger.error("❌ BLOQUEADO - Página muy pequeña")
            return False
        elif "salvum" in page_source or "usuario" in page_source or "login" in page_source:
            logger.info("✅ ACCESO EXITOSO - Página de Salvum detectada!")
            
            # MÉTODO MEJORADO DE LOGIN
            return realizar_login_mejorado(driver, wait)
        else:
            logger.warning("❓ Estado desconocido de página")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error general: {e}")
        return False
        
    finally:
        if driver:
            driver.quit()

def realizar_login_mejorado(driver, wait):
    """Método mejorado para realizar login en Salvum"""
    logger.info("🔑 INICIANDO PROCESO DE LOGIN MEJORADO")
    logger.info("-" * 50)
    
    try:
        # Obtener credenciales
        usuario = os.getenv('SALVUM_USER', 'Molivaco')
        password = os.getenv('SALVUM_PASS', 'd6r4YaXN')
        
        logger.info(f"👤 Usuario: {usuario}")
        logger.info("🔒 Password: [PROTEGIDO]")
        
        # MÉTODO 1: Selectores específicos mejorados
        logger.info("🔍 Método 1: Buscando campos con selectores específicos...")
        
        campo_usuario = None
        campo_password = None
        
        # Intentar múltiples selectores para usuario
        selectores_usuario = [
            "input[type='text']",
            "input[name*='user']",
            "input[name*='usuario']", 
            "input[id*='user']",
            "input[id*='usuario']",
            "input[placeholder*='Usuario']",
            "input[placeholder*='usuario']"
        ]
        
        for selector in selectores_usuario:
            try:
                campos = driver.find_elements(By.CSS_SELECTOR, selector)
                for campo in campos:
                    if campo.is_displayed() and campo.is_enabled():
                        campo_usuario = campo
                        logger.info(f"✅ Campo usuario encontrado con: {selector}")
                        break
                if campo_usuario:
                    break
            except:
                continue
        
        # Buscar campo password
        try:
            campo_password = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            logger.info("✅ Campo password encontrado")
        except:
            logger.error("❌ No se encontró campo password")
            return False
        
        # MÉTODO 2: Si no encontró usuario, usar posición
        if not campo_usuario:
            logger.info("🔍 Método 2: Buscando por posición...")
            try:
                inputs_visibles = []
                todos_inputs = driver.find_elements(By.TAG_NAME, "input")
                
                for inp in todos_inputs:
                    if inp.is_displayed() and inp.is_enabled():
                        tipo = inp.get_attribute('type') or 'text'
                        if tipo != 'password':
                            inputs_visibles.append(inp)
                
                if inputs_visibles:
                    campo_usuario = inputs_visibles[0]
                    logger.info("✅ Campo usuario por posición")
            except Exception as e:
                logger.error(f"Error buscando por posición: {e}")
                return False
        
        if not campo_usuario or not campo_password:
            logger.error("❌ No se encontraron ambos campos")
            return False
        
        # LLENAR CAMPOS CON MÉTODO MEJORADO
        logger.info("✏️ Llenando campos con método mejorado...")
        
        # Scroll y focus en usuario
        driver.execute_script("arguments[0].scrollIntoView(true);", campo_usuario)
        time.sleep(2)
        driver.execute_script("arguments[0].focus();", campo_usuario)
        time.sleep(1)
        
        # Limpiar y llenar usuario
        campo_usuario.clear()
        time.sleep(1)
        campo_usuario.send_keys(usuario)
        logger.info("✅ Usuario ingresado")
        time.sleep(2)
        
        # Focus en password
        driver.execute_script("arguments[0].focus();", campo_password)
        time.sleep(1)
        
        # Limpiar y llenar password
        campo_password.clear()
        time.sleep(1)
        campo_password.send_keys(password)
        logger.info("✅ Password ingresado")
        time.sleep(2)
        
        # Screenshot antes de submit
        driver.save_screenshot('salvum_antes_submit.png')
        logger.info("📸 Screenshot antes de submit")
        
        # BUSCAR Y HACER CLICK EN BOTÓN
        logger.info("🔘 Buscando botón de submit...")
        
        boton_submit = None
        
        # Método 1: Por tipo submit
        try:
            boton_submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            logger.info("✅ Botón submit encontrado por tipo")
        except:
            pass
        
        # Método 2: Por texto
        if not boton_submit:
            try:
                boton_submit = driver.find_element(By.XPATH, "//button[contains(text(), 'INGRESAR') or contains(text(), 'Ingresar') or contains(text(), 'LOGIN')]")
                logger.info("✅ Botón submit encontrado por texto")
            except:
                pass
        
        # Método 3: Primer botón disponible
        if not boton_submit:
            try:
                botones = driver.find_elements(By.TAG_NAME, "button")
                for btn in botones:
                    if btn.is_displayed() and btn.is_enabled():
                        boton_submit = btn
                        logger.info("✅ Usando primer botón disponible")
                        break
            except:
                pass
        
        # EJECUTAR SUBMIT
        if boton_submit:
            try:
                # Scroll al botón
                driver.execute_script("arguments[0].scrollIntoView(true);", boton_submit)
                time.sleep(2)
                
                # Click con JavaScript como backup
                try:
                    boton_submit.click()
                    logger.info("🔘 Click normal ejecutado")
                except:
                    driver.execute_script("arguments[0].click();", boton_submit)
                    logger.info("🔘 Click con JavaScript ejecutado")
                    
            except Exception as e:
                logger.error(f"Error en click: {e}")
                # Último recurso: Enter en password
                campo_password.send_keys(Keys.RETURN)
                logger.info("⌨️ Enter enviado como último recurso")
        else:
            # No hay botón, usar Enter
            campo_password.send_keys(Keys.RETURN)
            logger.info("⌨️ Enter enviado (no se encontró botón)")
        
        # ESPERAR RESPUESTA
        logger.info("⏳ Esperando respuesta del servidor...")
        time.sleep(12)  # Espera más larga
        
        # Screenshot después de submit
        driver.save_screenshot('salvum_despues_submit.png')
        logger.info("📸 Screenshot después de submit")
        
        # VERIFICAR RESULTADO
        nueva_url = driver.current_url
        nuevo_titulo = driver.title
        
        logger.info(f"📍 Nueva URL: {nueva_url}")
        logger.info(f"📄 Nuevo título: {nuevo_titulo}")
        
        # Verificar si hay mensajes de error
        try:
            page_text = driver.page_source.lower()
            if "incorrecto" in page_text or "error" in page_text:
                logger.warning("⚠️ Posible mensaje de error detectado")
        except:
            pass
        
        # Determinar éxito del login
        if nueva_url != "https://prescriptores.salvum.cl/login" and "login" not in nueva_url.lower():
            logger.info("🎉 ¡LOGIN EXITOSO! - URL cambió")
            
            # Buscar indicadores de login exitoso
            try:
                elementos_post_login = driver.find_elements(By.CSS_SELECTOR, 
                    "nav, .menu, .dashboard, .logout, .profile, [class*='menu'], [class*='nav']")
                if elementos_post_login:
                    logger.info(f"✅ {len(elementos_post_login)} elementos post-login encontrados")
            except:
                pass
                
            # Guardar resultado exitoso
            guardar_resultado("LOGIN_EXITOSO", nueva_url, nuevo_titulo, driver.page_source)
            return True
        else:
            logger.info("❌ Login falló - permanece en página de login")
            guardar_resultado("LOGIN_FALLO", nueva_url, nuevo_titulo, driver.page_source)
            return False
            
    except Exception as e:
        logger.error(f"❌ Error en proceso de login: {e}")
        return False

def guardar_resultado(resultado, url, titulo, page_source):
    """Guardar resultado detallado del test"""
    try:
        results = {
            'timestamp': datetime.now().isoformat(),
            'resultado': resultado,
            'url_final': url,
            'titulo_final': titulo,
            'html_size_final': len(page_source),
            'github_actions': True
        }
        
        with open('resultado_login.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        with open('login_test.log', 'w') as f:
            f.write(f"Resultado: {resultado}\n")
            f.write(f"URL: {url}\n")
            f.write(f"Título: {titulo}\n")
            f.write(f"Timestamp: {datetime.now()}\n")
            
        logger.info("💾 Resultado guardado en archivos")
        
    except Exception as e:
        logger.error(f"Error guardando resultado: {e}")

if __name__ == "__main__":
    print("🚀 SALVUM LOGIN TEST - VERSIÓN MEJORADA")
    print("=" * 60)
    
    success = test_salvum_login_mejorado()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ¡LOGIN EXITOSO EN SALVUM!")
        print("✅ GitHub Actions puede automatizar Salvum")
        print("🚀 Listo para automatización completa")
    else:
        print("❌ Login falló")
        print("🔍 Revisar logs y screenshots para más detalles")
        print("💡 Puede necesitar ajustes adicionales")
    print("=" * 60)
