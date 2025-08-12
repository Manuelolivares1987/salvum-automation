#!/usr/bin/env python3
"""
TEST DIAGNÓSTICO SALVUM - Identificar bloqueos específicos
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

def test_diagnostico_completo():
    """Test diagnóstico completo para identificar problemas específicos"""
    logger.info("🔍 DIAGNÓSTICO COMPLETO DE ACCESO A SALVUM")
    logger.info("=" * 70)
    
    resultados = {
        'timestamp': datetime.now().isoformat(),
        'tests': {},
        'recomendaciones': []
    }
    
    # TEST 1: Verificación de red básica
    logger.info("\n🌐 TEST 1: VERIFICACIÓN DE RED BÁSICA")
    logger.info("-" * 40)
    
    try:
        # IP y ubicación
        response = requests.get('https://ipinfo.io/json', timeout=10)
        ip_data = response.json()
        
        logger.info(f"📍 IP: {ip_data.get('ip')}")
        logger.info(f"🏙️ Ciudad: {ip_data.get('city')}")
        logger.info(f"🏢 País: {ip_data.get('country')}")
        logger.info(f"🏢 ISP: {ip_data.get('org')}")
        logger.info(f"🌍 Región: {ip_data.get('region')}")
        
        resultados['tests']['ip_info'] = ip_data
        
        # ¿Es Chile?
        es_chile = ip_data.get('country') == 'CL'
        logger.info(f"🇨🇱 Acceso desde Chile: {'✅ SÍ' if es_chile else '❌ NO'}")
        
        if not es_chile:
            resultados['recomendaciones'].append("CRÍTICO: Acceso desde fuera de Chile - probable bloqueo geográfico")
            
    except Exception as e:
        logger.error(f"❌ Error verificando IP: {e}")
        resultados['tests']['ip_info'] = {'error': str(e)}
    
    # TEST 2: Conectividad HTTP a Salvum
    logger.info("\n🔗 TEST 2: CONECTIVIDAD HTTP A SALVUM")
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
            response = requests.get(url, timeout=15, allow_redirects=True)
            
            logger.info(f"  📊 Código: {response.status_code}")
            logger.info(f"  📍 URL final: {response.url}")
            logger.info(f"  📄 Tamaño: {len(response.content)} bytes")
            
            # Verificar contenido
            contenido = response.text.lower()
            
            if response.status_code == 403:
                logger.error(f"  ❌ BLOQUEADO (403) - Acceso denegado")
                resultados['recomendaciones'].append(f"BLOQUEADO: {url} devuelve 403 - restricción geográfica/IP")
                
            elif response.status_code == 200:
                if 'salvum' in contenido:
                    logger.info(f"  ✅ ACCESO OK - Contenido Salvum detectado")
                elif 'bbva' in contenido:
                    logger.warning(f"  ⚠️ REDIRIGIDO A BBVA")
                    resultados['recomendaciones'].append("REDIRIGIDO: Salvum redirige a BBVA - posible bloqueo")
                else:
                    logger.warning(f"  ⚠️ Contenido desconocido")
            else:
                logger.warning(f"  ⚠️ Código inesperado: {response.status_code}")
            
            resultados['tests'][f'http_{url}'] = {
                'status_code': response.status_code,
                'final_url': response.url,
                'content_size': len(response.content),
                'content_sample': contenido[:200]
            }
            
        except Exception as e:
            logger.error(f"  ❌ Error: {e}")
            resultados['tests'][f'http_{url}'] = {'error': str(e)}
    
    # TEST 3: Headers y User Agent
    logger.info("\n🌐 TEST 3: HEADERS Y USER AGENT")
    logger.info("-" * 40)
    
    headers_test = [
        # Headers normales
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        # Headers "chilenos"
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
    ]
    
    for i, headers in enumerate(headers_test, 1):
        try:
            logger.info(f"Probando headers set {i}...")
            response = requests.get('https://prescriptores.salvum.cl/login', 
                                  headers=headers, timeout=15, allow_redirects=True)
            
            logger.info(f"  📊 Resultado: {response.status_code}")
            logger.info(f"  📍 URL final: {response.url}")
            
            resultados['tests'][f'headers_set_{i}'] = {
                'status_code': response.status_code,
                'final_url': response.url,
                'headers_sent': headers
            }
            
        except Exception as e:
            logger.error(f"  ❌ Error con headers {i}: {e}")
    
    # TEST 4: Test con Selenium (más realista)
    logger.info("\n🤖 TEST 4: ACCESO CON NAVEGADOR (SELENIUM)")
    logger.info("-" * 40)
    
    driver = None
    try:
        # Configurar Chrome
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        # User agent chileno
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--lang=es-CL')
        options.add_argument('--accept-language=es-CL,es;q=0.9,en;q=0.8')
        
        # Anti-detección básica
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Script anti-detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("Accediendo con navegador...")
        driver.get("https://prescriptores.salvum.cl/login")
        time.sleep(8)
        
        url_final = driver.current_url
        titulo = driver.title
        html_size = len(driver.page_source)
        
        logger.info(f"📍 URL final: {url_final}")
        logger.info(f"📄 Título: {titulo}")
        logger.info(f"📊 HTML size: {html_size}")
        
        # Guardar screenshot
        driver.save_screenshot('diagnostico_selenium.png')
        
        # Analizar contenido
        page_source = driver.page_source.lower()
        
        if "bbva" in titulo.lower():
            logger.error("❌ REDIRIGIDO A BBVA - Bloqueo confirmado")
            resultados['recomendaciones'].append("CONFIRMADO: Selenium también es redirigido a BBVA")
        elif html_size < 5000:
            logger.error("❌ PÁGINA MUY PEQUEÑA - Posible bloqueo")
        elif "salvum" in page_source or "login" in page_source:
            logger.info("✅ ACCESO EXITOSO CON SELENIUM")
            
            # Test básico de campos
            try:
                campos_login = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='password']")
                logger.info(f"🔍 Campos de login encontrados: {len(campos_login)}")
                
                if len(campos_login) >= 2:
                    logger.info("✅ Formulario de login disponible")
                else:
                    logger.warning("⚠️ Formulario incompleto o no encontrado")
                    
            except Exception as e:
                logger.error(f"Error verificando campos: {e}")
        else:
            logger.warning("❓ Contenido desconocido")
        
        # Guardar HTML para análisis
        with open('diagnostico_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        
        resultados['tests']['selenium'] = {
            'final_url': url_final,
            'title': titulo,
            'html_size': html_size,
            'success': "salvum" in page_source or "login" in page_source
        }
        
    except Exception as e:
        logger.error(f"❌ Error con Selenium: {e}")
        resultados['tests']['selenium'] = {'error': str(e)}
    finally:
        if driver:
            driver.quit()
    
    # TEST 5: Verificar credenciales (sin usarlas)
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
        resultados['recomendaciones'].append("CONFIGURACIÓN: Verificar que las credenciales estén configuradas correctamente")
    
    # ANÁLISIS FINAL Y RECOMENDACIONES
    logger.info("\n📊 ANÁLISIS FINAL")
    logger.info("=" * 70)
    
    # Determinar problema principal
    if not ip_data.get('country') == 'CL':
        logger.error("🚨 PROBLEMA PRINCIPAL: ACCESO DESDE FUERA DE CHILE")
        logger.error("   Salvum está bloqueando geográficamente GitHub Actions")
        resultados['problema_principal'] = 'BLOQUEO_GEOGRAFICO'
        
        logger.info("\n💡 SOLUCIONES POSIBLES:")
        logger.info("   1. Usar un proxy/VPN chileno")
        logger.info("   2. Usar un servidor en Chile")
        logger.info("   3. Contactar a Salvum para whitelisting")
        logger.info("   4. Ejecutar desde un servidor local chileno")
        
    elif resultados['tests'].get('selenium', {}).get('success'):
        logger.info("✅ ACCESO BÁSICO FUNCIONA")
        logger.info("   El problema puede estar en el proceso de login específico")
        resultados['problema_principal'] = 'PROCESO_LOGIN'
        
    else:
        logger.warning("❓ PROBLEMA DESCONOCIDO")
        logger.info("   Revisar logs detallados para más información")
        resultados['problema_principal'] = 'DESCONOCIDO'
    
    # Guardar resultados
    with open('diagnostico_completo.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    
    logger.info("\n💾 Diagnóstico completo guardado en 'diagnostico_completo.json'")
    logger.info("📸 Screenshots guardados para análisis visual")
    
    return resultados

def generar_reporte_final(resultados):
    """Generar reporte final con recomendaciones específicas"""
    logger.info("\n📋 REPORTE FINAL")
    logger.info("=" * 70)
    
    problema = resultados.get('problema_principal', 'DESCONOCIDO')
    
    if problema == 'BLOQUEO_GEOGRAFICO':
        logger.info("🚨 DIAGNÓSTICO: BLOQUEO GEOGRÁFICO CONFIRMADO")
        logger.info("   Salvum está bloqueando accesos desde fuera de Chile")
        logger.info("\n🔧 ACCIONES RECOMENDADAS:")
        logger.info("   1. INMEDIATA: Usar proxy chileno en el workflow")
        logger.info("   2. MEDIANO PLAZO: Servidor en Chile para GitHub Actions")
        logger.info("   3. LARGO PLAZO: Contactar Salvum para whitelist")
        
    elif problema == 'PROCESO_LOGIN':
        logger.info("✅ ACCESO BÁSICO: OK")
        logger.info("❌ PROCESO LOGIN: FALLA")
        logger.info("\n🔧 ACCIONES RECOMENDADAS:")
        logger.info("   1. Revisar cambios en la UI de Salvum")
        logger.info("   2. Verificar credenciales")
        logger.info("   3. Ajustar selectores de campos")
        
    else:
        logger.info("❓ DIAGNÓSTICO: REQUIERE ANÁLISIS ADICIONAL")
        logger.info("\n🔧 ACCIONES RECOMENDADAS:")
        logger.info("   1. Revisar archivos de diagnóstico generados")
        logger.info("   2. Verificar conectividad desde otro entorno")
        logger.info("   3. Contactar soporte técnico")
    
    logger.info("\n📁 ARCHIVOS GENERADOS:")
    logger.info("   📊 diagnostico_completo.json - Resultados detallados")
    logger.info("   📸 diagnostico_selenium.png - Screenshot del navegador")
    logger.info("   📄 diagnostico_page.html - HTML de la página")

if __name__ == "__main__":
    print("🔍 DIAGNÓSTICO COMPLETO DE ACCESO A SALVUM")
    print("=" * 70)
    print("Este script identificará el problema específico con el acceso a Salvum")
    print("=" * 70)
    
    try:
        resultados = test_diagnostico_completo()
        generar_reporte_final(resultados)
        
        problema = resultados.get('problema_principal', 'DESCONOCIDO')
        if problema == 'BLOQUEO_GEOGRAFICO':
            exit(1)  # Error code para bloqueo geográfico
        elif problema == 'PROCESO_LOGIN':
            exit(2)  # Error code para problemas de login
        else:
            exit(0)  # Éxito o problema desconocido
            
    except Exception as e:
        logger.error(f"❌ Error en diagnóstico: {e}")
        exit(3)  # Error general
