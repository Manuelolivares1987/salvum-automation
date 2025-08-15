#!/usr/bin/env python3
"""
SALVUM AUTOMATION CON VPS CHILE - Diagnóstico Completo y Automatización
Usando túnel SOCKS al VPS chileno (45.7.230.109)
"""
import os
import time
import json
import requests
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

# Configuración del proxy SOCKS al VPS Chile
SOCKS_PROXY = "socks5://localhost:8080"
VPS_IP_ESPERADA = "45.7.230.109"  # IP de tu VPS

def configurar_requests_con_proxy():
    """Configurar requests para usar el proxy SOCKS del VPS Chile"""
    proxies = {
        'http': SOCKS_PROXY,
        'https': SOCKS_PROXY
    }
    return proxies

def configurar_chrome_con_proxy():
    """Configurar Chrome para usar el proxy SOCKS del VPS Chile"""
    options = Options()
    
    # Configuración básica
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # ⭐ CONFIGURACIÓN PROXY SOCKS PARA VPS CHILE ⭐
    options.add_argument(f'--proxy-server={SOCKS_PROXY}')
    options.add_argument('--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE localhost')
    
    # User agent chileno realista
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--lang=es-CL')
    options.add_argument('--accept-language=es-CL,es;q=0.9,en;q=0.8')
    
    # Anti-detección
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Crear driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Script anti-detección
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def verificar_conexion_vps():
    """Verificar que estamos conectados correctamente al VPS Chile"""
    logger.info("🔍 VERIFICANDO CONEXIÓN AL VPS CHILE")
    logger.info("-" * 50)
    
    try:
        proxies = configurar_requests_con_proxy()
        
        # Verificar IP
        response = requests.get('https://ipinfo.io/json', 
                              proxies=proxies, 
                              timeout=15)
        ip_data = response.json()
        
        ip_actual = ip_data.get('ip')
        pais = ip_data.get('country')
        ciudad = ip_data.get('city')
        
        logger.info(f"📍 IP actual: {ip_actual}")
        logger.info(f"🏢 País: {pais}")
        logger.info(f"🏙️ Ciudad: {ciudad}")
        
        # Verificar que es nuestro VPS
        if ip_actual == VPS_IP_ESPERADA:
            logger.info(f"✅ PERFECTO: Usando VPS chileno ({VPS_IP_ESPERADA})")
        else:
            logger.warning(f"⚠️ IP diferente a la esperada. Esperada: {VPS_IP_ESPERADA}, Actual: {ip_actual}")
        
        # Verificar que es Chile
        if pais == 'CL':
            logger.info("🇨🇱 ✅ CONFIRMADO: Conexión desde Chile")
            return True, ip_data
        else:
            logger.error(f"❌ ERROR: No estamos en Chile. País detectado: {pais}")
            return False, ip_data
            
    except Exception as e:
        logger.error(f"❌ Error verificando conexión VPS: {e}")
        return False, {'error': str(e)}

def test_diagnostico_con_vps():
    """Test diagnóstico completo usando el VPS chileno"""
    logger.info("🔍 DIAGNÓSTICO COMPLETO VIA VPS CHILE")
    logger.info("=" * 70)
    
    resultados = {
        'timestamp': datetime.now().isoformat(),
        'vps_ip': VPS_IP_ESPERADA,
        'tests': {},
        'recomendaciones': []
    }
    
    # TEST 1: Verificación de conexión VPS
    logger.info("\n🔗 TEST 1: VERIFICACIÓN CONEXIÓN VPS")
    logger.info("-" * 40)
    
    vps_ok, ip_data = verificar_conexion_vps()
    resultados['tests']['vps_connection'] = {
        'success': vps_ok,
        'ip_data': ip_data
    }
    
    if not vps_ok:
        logger.error("❌ CRÍTICO: No se puede usar el VPS Chile")
        resultados['problema_principal'] = 'VPS_CONNECTION_FAILED'
        return resultados
    
    # Configurar proxies para el resto de tests
    proxies = configurar_requests_con_proxy()
    
    # TEST 2: Conectividad HTTP a Salvum via VPS
    logger.info("\n🔗 TEST 2: CONECTIVIDAD HTTP A SALVUM VIA VPS")
    logger.info("-" * 40)
    
    urls_test = [
        'https://prescriptores.salvum.cl/',
        'https://prescriptores.salvum.cl/login',
        'https://salvum.cl/',
        'https://www.salvum.cl/'
    ]
    
    for url in urls_test:
        try:
            logger.info(f"Probando: {url}")
            response = requests.get(url, 
                                  proxies=proxies, 
                                  timeout=20, 
                                  allow_redirects=True)
            
            logger.info(f"  📊 Código: {response.status_code}")
            logger.info(f"  📍 URL final: {response.url}")
            logger.info(f"  📄 Tamaño: {len(response.content)} bytes")
            
            # Verificar contenido
            contenido = response.text.lower()
            
            if response.status_code == 403:
                logger.error(f"  ❌ BLOQUEADO (403) - Aún con IP chilena!")
                resultados['recomendaciones'].append(f"BLOQUEADO: {url} devuelve 403 incluso con VPS Chile")
                
            elif response.status_code == 200:
                if 'salvum' in contenido:
                    logger.info(f"  ✅ ACCESO OK - Contenido Salvum detectado")
                elif 'bbva' in contenido:
                    logger.warning(f"  ⚠️ REDIRIGIDO A BBVA (aún con IP chilena)")
                    resultados['recomendaciones'].append("REDIRIGIDO: Aún redirige a BBVA con IP chilena")
                else:
                    logger.warning(f"  ⚠️ Contenido desconocido")
            else:
                logger.warning(f"  ⚠️ Código inesperado: {response.status_code}")
            
            resultados['tests'][f'http_vps_{url}'] = {
                'status_code': response.status_code,
                'final_url': response.url,
                'content_size': len(response.content),
                'content_sample': contenido[:200]
            }
            
        except Exception as e:
            logger.error(f"  ❌ Error: {e}")
            resultados['tests'][f'http_vps_{url}'] = {'error': str(e)}
    
    # TEST 3: Headers específicos con VPS
    logger.info("\n🌐 TEST 3: HEADERS CHILENOS VIA VPS")
    logger.info("-" * 40)
    
    headers_chilenos = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        logger.info("Probando con headers chilenos optimizados...")
        response = requests.get('https://prescriptores.salvum.cl/login', 
                              headers=headers_chilenos,
                              proxies=proxies, 
                              timeout=20, 
                              allow_redirects=True)
        
        logger.info(f"  📊 Resultado: {response.status_code}")
        logger.info(f"  📍 URL final: {response.url}")
        
        resultados['tests']['headers_chilenos_vps'] = {
            'status_code': response.status_code,
            'final_url': response.url,
            'headers_sent': headers_chilenos
        }
        
    except Exception as e:
        logger.error(f"  ❌ Error con headers chilenos: {e}")
    
    # TEST 4: Test con Selenium via VPS
    logger.info("\n🤖 TEST 4: ACCESO CON NAVEGADOR VIA VPS")
    logger.info("-" * 40)
    
    driver = None
    try:
        driver = configurar_chrome_con_proxy()
        
        # Verificar IP del navegador
        logger.info("🔍 Verificando IP del navegador...")
        driver.get("https://ipinfo.io/json")
        time.sleep(3)
        
        try:
            ip_browser = driver.find_element(By.TAG_NAME, 'pre').text
            ip_data_browser = json.loads(ip_browser)
            logger.info(f"📍 IP navegador: {ip_data_browser.get('ip')}")
            logger.info(f"🏢 País navegador: {ip_data_browser.get('country')}")
            
            if ip_data_browser.get('ip') == VPS_IP_ESPERADA:
                logger.info("✅ Navegador usando VPS correctamente")
            else:
                logger.warning("⚠️ Navegador no usa la IP del VPS")
                
        except Exception as e:
            logger.warning(f"No se pudo verificar IP del navegador: {e}")
        
        logger.info("🔗 Accediendo a Salvum con navegador...")
        driver.get("https://prescriptores.salvum.cl/login")
        time.sleep(10)
        
        url_final = driver.current_url
        titulo = driver.title
        html_size = len(driver.page_source)
        
        logger.info(f"📍 URL final: {url_final}")
        logger.info(f"📄 Título: {titulo}")
        logger.info(f"📊 HTML size: {html_size}")
        
        # Guardar screenshot
        driver.save_screenshot('salvum_vps_test.png')
        
        # Analizar contenido
        page_source = driver.page_source.lower()
        
        if "bbva" in titulo.lower():
            logger.error("❌ REDIRIGIDO A BBVA - Incluso con VPS Chile")
            resultados['recomendaciones'].append("CRÍTICO: Aún redirige a BBVA con VPS Chile")
            resultados['problema_principal'] = 'BBVA_REDIRECT_PERSISTENT'
        elif html_size < 5000:
            logger.error("❌ PÁGINA MUY PEQUEÑA - Posible bloqueo")
            resultados['problema_principal'] = 'PAGE_TOO_SMALL'
        elif "salvum" in page_source or "login" in page_source:
            logger.info("✅ ACCESO EXITOSO CON VPS + SELENIUM")
            
            # Test de campos de login
            try:
                campos_login = driver.find_elements(By.CSS_SELECTOR, 
                    "input[type='text'], input[type='email'], input[name*='usuario'], input[name*='email']")
                campos_password = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                
                logger.info(f"🔍 Campos texto encontrados: {len(campos_login)}")
                logger.info(f"🔍 Campos password encontrados: {len(campos_password)}")
                
                if len(campos_login) >= 1 and len(campos_password) >= 1:
                    logger.info("✅ FORMULARIO DE LOGIN DISPONIBLE")
                    resultados['problema_principal'] = 'SUCCESS'
                    
                    # Intentar login real si tenemos credenciales
                    if os.getenv('SALVUM_USER') and os.getenv('SALVUM_PASS'):
                        logger.info("🔐 Intentando login real...")
                        resultado_login = intentar_login_salvum(driver)
                        resultados['tests']['login_real'] = resultado_login
                    else:
                        logger.info("ℹ️ Sin credenciales para test de login")
                else:
                    logger.warning("⚠️ Formulario incompleto")
                    resultados['problema_principal'] = 'INCOMPLETE_FORM'
                    
            except Exception as e:
                logger.error(f"Error verificando campos: {e}")
        else:
            logger.warning("❓ Contenido desconocido")
            resultados['problema_principal'] = 'UNKNOWN_CONTENT'
        
        # Guardar HTML para análisis
        with open('salvum_vps_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        
        resultados['tests']['selenium_vps'] = {
            'final_url': url_final,
            'title': titulo,
            'html_size': html_size,
            'success': "salvum" in page_source or "login" in page_source
        }
        
    except Exception as e:
        logger.error(f"❌ Error con Selenium + VPS: {e}")
        resultados['tests']['selenium_vps'] = {'error': str(e)}
    finally:
        if driver:
            driver.quit()
    
    # TEST 5: Verificar credenciales
    logger.info("\n🔐 TEST 5: VERIFICACIÓN DE CREDENCIALES")
    logger.info("-" * 40)
    
    usuario = os.getenv('SALVUM_USER')
    password = os.getenv('SALVUM_PASS')
    
    logger.info(f"👤 SALVUM_USER: {'✅ CONFIGURADO' if usuario else '❌ NO CONFIGURADO'}")
    logger.info(f"🔒 SALVUM_PASS: {'✅ CONFIGURADO' if password else '❌ NO CONFIGURADO'}")
    
    if usuario:
        logger.info(f"👤 Usuario: {usuario}")
        logger.info(f"📏 Longitud password: {len(password) if password else 0} caracteres")
    
    resultados['tests']['credentials'] = {
        'user_set': bool(usuario),
        'pass_set': bool(password),
        'user_value': usuario,
        'pass_length': len(password) if password else 0
    }
    
    if not usuario or not password:
        resultados['recomendaciones'].append("CONFIGURACIÓN: Verificar credenciales en GitHub Secrets")
    
    return resultados

def intentar_login_salvum(driver):
    """Intentar login real en Salvum"""
    logger.info("🔐 INTENTANDO LOGIN REAL EN SALVUM")
    logger.info("-" * 40)
    
    resultado = {
        'intentado': True,
        'exitoso': False,
        'error': None,
        'pasos': []
    }
    
    try:
        usuario = os.getenv('SALVUM_USER')
        password = os.getenv('SALVUM_PASS')
        
        # Buscar campos de login
        resultado['pasos'].append("Buscando campos de login...")
        
        # Intentar múltiples selectores para usuario
        selectores_usuario = [
            "input[type='text']",
            "input[type='email']", 
            "input[name*='usuario']",
            "input[name*='email']",
            "input[name*='user']",
            "input[id*='usuario']",
            "input[id*='email']"
        ]
        
        campo_usuario = None
        for selector in selectores_usuario:
            try:
                campo_usuario = driver.find_element(By.CSS_SELECTOR, selector)
                if campo_usuario:
                    logger.info(f"✅ Campo usuario encontrado: {selector}")
                    break
            except:
                continue
        
        if not campo_usuario:
            resultado['error'] = "No se encontró campo de usuario"
            return resultado
        
        # Buscar campo password
        try:
            campo_password = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            logger.info("✅ Campo password encontrado")
        except:
            resultado['error'] = "No se encontró campo de password"
            return resultado
        
        # Limpiar y llenar campos
        resultado['pasos'].append("Llenando credenciales...")
        campo_usuario.clear()
        time.sleep(1)
        campo_usuario.send_keys(usuario)
        
        time.sleep(1)
        campo_password.clear()
        time.sleep(1)
        campo_password.send_keys(password)
        
        # Buscar botón de login
        resultado['pasos'].append("Buscando botón de login...")
        selectores_boton = [
            "button[type='submit']",
            "input[type='submit']",
            "button:contains('Ingresar')",
            "button:contains('Login')",
            "button:contains('Entrar')",
            ".btn-primary",
            ".btn-login"
        ]
        
        boton_login = None
        for selector in selectores_boton:
            try:
                boton_login = driver.find_element(By.CSS_SELECTOR, selector)
                if boton_login:
                    logger.info(f"✅ Botón login encontrado: {selector}")
                    break
            except:
                continue
        
        if not boton_login:
            # Intentar submit con Enter
            resultado['pasos'].append("Intentando submit con Enter...")
            campo_password.send_keys(Keys.RETURN)
        else:
            resultado['pasos'].append("Haciendo clic en botón de login...")
            boton_login.click()
        
        # Esperar respuesta
        resultado['pasos'].append("Esperando respuesta del login...")
        time.sleep(8)
        
        # Verificar si el login fue exitoso
        url_despues = driver.current_url
        titulo_despues = driver.title
        
        logger.info(f"📍 URL después del login: {url_despues}")
        logger.info(f"📄 Título después del login: {titulo_despues}")
        
        # Guardar screenshot después del login
        driver.save_screenshot('salvum_after_login.png')
        
        # Verificar éxito
        if "login" not in url_despues.lower() or "dashboard" in url_despues.lower():
            logger.info("✅ LOGIN EXITOSO - URL cambió apropiadamente")
            resultado['exitoso'] = True
            resultado['pasos'].append("Login exitoso confirmado")
        else:
            logger.warning("⚠️ Login posiblemente fallido - URL no cambió")
            resultado['pasos'].append("Login posiblemente fallido")
        
        resultado['url_final'] = url_despues
        resultado['titulo_final'] = titulo_despues
        
    except Exception as e:
        logger.error(f"❌ Error durante login: {e}")
        resultado['error'] = str(e)
        driver.save_screenshot('salvum_login_error.png')
    
    return resultado

def ejecutar_automatizacion_completa():
    """Ejecutar la automatización completa si el diagnóstico es exitoso"""
    logger.info("🤖 EJECUTANDO AUTOMATIZACIÓN COMPLETA")
    logger.info("-" * 50)
    
    driver = None
    try:
        driver = configurar_chrome_con_proxy()
        
        # Login
        driver.get("https://prescriptores.salvum.cl/login")
        time.sleep(8)
        
        resultado_login = intentar_login_salvum(driver)
        
        if not resultado_login['exitoso']:
            logger.error("❌ No se pudo completar el login, abortando automatización")
            return False
        
        logger.info("✅ Login exitoso, continuando con automatización...")
        
        # Aquí iría tu lógica específica de automatización
        # Por ejemplo: navegar a secciones, extraer datos, etc.
        
        logger.info("🎉 AUTOMATIZACIÓN COMPLETADA EXITOSAMENTE")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en automatización: {e}")
        return False
    finally:
        if driver:
            driver.quit()

def generar_reporte_final(resultados):
    """Generar reporte final con recomendaciones específicas"""
    logger.info("\n📋 REPORTE FINAL - VPS CHILE")
    logger.info("=" * 70)
    
    problema = resultados.get('problema_principal', 'DESCONOCIDO')
    vps_connection = resultados.get('tests', {}).get('vps_connection', {}).get('success', False)
    
    if not vps_connection:
        logger.error("🚨 CRÍTICO: CONEXIÓN AL VPS CHILE FALLÓ")
        logger.info("🔧 VERIFICAR:")
        logger.info("   1. Túnel SSH está activo (puerto 8080)")
        logger.info("   2. Credenciales del VPS son correctas")
        logger.info("   3. Firewall no bloquea conexiones")
        
    elif problema == 'SUCCESS':
        logger.info("🎉 ¡ÉXITO COMPLETO!")
        logger.info("✅ VPS Chile funcionando correctamente")
        logger.info("✅ Acceso a Salvum confirmado")
        logger.info("✅ Formulario de login disponible")
        
    elif problema == 'BBVA_REDIRECT_PERSISTENT':
        logger.error("🚨 PROBLEMA: AÚN REDIRIGE A BBVA")
        logger.info("   Incluso con IP chilena, Salvum redirige a BBVA")
        logger.info("🔧 POSIBLES CAUSAS:")
        logger.info("   1. Bloqueo por User-Agent de automatización")
        logger.info("   2. Restricciones adicionales (hora, etc.)")
        logger.info("   3. Problema temporal en Salvum")
        
    else:
        logger.warning(f"❓ PROBLEMA: {problema}")
        logger.info("🔧 REVISAR archivos de diagnóstico generados")
    
    logger.info(f"\n📊 VPS IP utilizada: {VPS_IP_ESPERADA}")
    logger.info(f"🕐 Timestamp: {resultados.get('timestamp')}")
    
    logger.info("\n📁 ARCHIVOS GENERADOS:")
    logger.info("   📊 diagnostico_vps_completo.json - Resultados detallados")
    logger.info("   📸 salvum_vps_test.png - Screenshot acceso")
    logger.info("   📄 salvum_vps_page.html - HTML de la página")
    logger.info("   📸 salvum_after_login.png - Screenshot post-login (si aplica)")

def main():
    """Función principal"""
    print("🇨🇱 SALVUM AUTOMATION CON VPS CHILE")
    print("=" * 70)
    print(f"VPS IP: {VPS_IP_ESPERADA}")
    print(f"Proxy: {SOCKS_PROXY}")
    print("=" * 70)
    
    try:
        # Verificar si estamos en modo test
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        
        if test_mode:
            logger.info("🧪 MODO TEST - Solo diagnóstico")
            resultados = test_diagnostico_con_vps()
        else:
            logger.info("🚀 MODO COMPLETO - Diagnóstico + Automatización")
            resultados = test_diagnostico_con_vps()
            
            if resultados.get('problema_principal') == 'SUCCESS':
                exito_automatizacion = ejecutar_automatizacion_completa()
                resultados['automatizacion_exitosa'] = exito_automatizacion
            else:
                logger.warning("⚠️ Diagnóstico no exitoso, saltando automatización")
        
        # Guardar resultados
        with open('diagnostico_vps_completo.json', 'w', encoding='utf-8') as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        
        generar_reporte_final(resultados)
        
        # Códigos de salida
        problema = resultados.get('problema_principal', 'DESCONOCIDO')
        if problema == 'SUCCESS':
            exit(0)  # Éxito
        elif problema == 'VPS_CONNECTION_FAILED':
            exit(1)  # Error de conexión VPS
        elif problema == 'BBVA_REDIRECT_PERSISTENT':
            exit(2)  # Redirigido a BBVA
        else:
            exit(3)  # Otros problemas
            
    except Exception as e:
        logger.error(f"❌ Error general: {e}")
        exit(4)  # Error general

if __name__ == "__main__":
    main()
