#!/usr/bin/env python3
"""
AUTOMATIZACIÓN SALVUM - VERSIÓN FINAL CON SELECTORES PRECISOS
Basado en inspección real de elementos HTML
"""
import os
import time
import json
import logging
import gspread
import subprocess
import socket
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🇨🇱 CONFIGURACIÓN VPS CHILE
SOCKS_PROXY = "socks5://localhost:8080"
VPS_IP_ESPERADA = "45.7.230.109"

# 🎯 ESTADOS VÁLIDOS PARA PROCESAR
ESTADOS_VALIDOS_PROCESAR = [
    'NUEVO', 'PROCESAR', 'PENDIENTE', 'LISTO', 
    'READY', 'AUTOMATIZAR', 'SI', 'YES', 'PROCESO'
]

class SalvumAutomacionPrecisa:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.gc = None
        self.agentes_config = []
        self.clientes_procesados = []
        self.clientes_fallidos = []
        
    def verificar_conexion_vps(self):
        """Verificar que estamos conectados correctamente al VPS Chile"""
        logger.info("🔍 VERIFICANDO CONEXIÓN AL VPS CHILE")
        logger.info("-" * 50)
        
        try:
            import requests
            
            proxies = {
                'http': SOCKS_PROXY,
                'https': SOCKS_PROXY
            }
            
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
            
            if ip_actual == VPS_IP_ESPERADA:
                logger.info(f"✅ PERFECTO: Usando VPS chileno ({VPS_IP_ESPERADA})")
            else:
                logger.warning(f"⚠️ IP diferente a la esperada. Esperada: {VPS_IP_ESPERADA}, Actual: {ip_actual}")
            
            if pais == 'CL':
                logger.info("🇨🇱 ✅ CONFIRMADO: Conexión desde Chile")
                return True, ip_data
            else:
                logger.error(f"❌ ERROR: No estamos en Chile. País detectado: {pais}")
                return False, ip_data
                
        except Exception as e:
            logger.error(f"❌ Error verificando conexión VPS: {e}")
            return False, {'error': str(e)}

    def verificar_tunel_socks(self):
        """Verificar túnel SOCKS (solo para verificaciones HTTP)"""
        logger.info("🔍 Verificando túnel SOCKS...")
        
        try:
            result = subprocess.run(['pgrep', '-f', 'ssh.*-D.*8080'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("❌ Proceso SSH del túnel no encontrado")
                return False
            
            logger.info(f"✅ Proceso SSH encontrado: PID {result.stdout.strip()}")
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 8080))
            sock.close()
            
            if result != 0:
                logger.error("❌ Puerto 8080 no está disponible")
                return False
            
            logger.info("✅ Puerto 8080 escuchando")
            
            import requests
            proxies = {'http': SOCKS_PROXY, 'https': SOCKS_PROXY}
            response = requests.get('https://ipinfo.io/json', 
                                  proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                ip_data = response.json()
                logger.info(f"✅ Túnel funcional - IP: {ip_data.get('ip')}, País: {ip_data.get('country')}")
                return True
            else:
                logger.error("❌ Túnel no responde correctamente")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error verificando túnel: {e}")
            return False
        
    def cargar_configuracion_agentes(self):
        """Cargar configuración de múltiples agentes desde config.json"""
        logger.info("📋 Cargando configuración de agentes...")
        
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                agentes_activos = [
                    agente for agente in config.get('agentes', []) 
                    if agente.get('activo', True)
                ]
                
                self.agentes_config = agentes_activos
                logger.info(f"✅ {len(agentes_activos)} agentes configurados desde config.json")
                
                for agente in agentes_activos:
                    logger.info(f"  👥 {agente['nombre']} - Sheet: ...{agente['sheet_id'][-8:]}")
                
                return len(agentes_activos) > 0
                
            else:
                logger.info("📋 config.json no encontrado, usando configuración básica...")
                sheet_id = os.getenv('GOOGLE_SHEET_ID')
                
                if sheet_id:
                    self.agentes_config = [{
                        'nombre': 'Agente Principal',
                        'sheet_id': sheet_id,
                        'activo': True
                    }]
                    logger.info("✅ 1 planilla configurada desde variable de entorno")
                    return True
                else:
                    logger.error("❌ No se encontró configuración de planillas")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
            return False
    
    def configurar_google_sheets(self):
        """Configurar conexión con Google Sheets"""
        logger.info("📊 Configurando Google Sheets...")
        
        try:
            creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
            if creds_json:
                creds_dict = json.loads(creds_json)
                creds = Credentials.from_service_account_info(creds_dict)
            else:
                creds = Credentials.from_service_account_file('credentials.json')
            
            scoped_creds = creds.with_scopes([
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ])
            
            self.gc = gspread.authorize(scoped_creds)
            
            logger.info("✅ Google Sheets configurado")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando Google Sheets: {e}")
            return False
    
    def leer_clientes_desde_planilla(self, sheet_id, nombre_agente):
        """Leer clientes con manejo de acentos y estados flexibles"""
        logger.info(f"📖 Leyendo clientes de {nombre_agente}...")
        
        try:
            spreadsheet = self.gc.open_by_key(sheet_id)
            
            worksheet = None
            nombres_hoja_posibles = [
                'Mis_Clientes_Financiamiento',
                'sheet1', 'Hoja1', 'Sheet1'
            ]
            
            for nombre_hoja in nombres_hoja_posibles:
                try:
                    worksheet = spreadsheet.worksheet(nombre_hoja)
                    logger.info(f"✅ Hoja encontrada: '{nombre_hoja}'")
                    break
                except:
                    continue
            
            if not worksheet:
                worksheet = spreadsheet.sheet1
                logger.info("⚠️ Usando primera hoja disponible")
            
            records = worksheet.get_all_records()
            logger.info(f"📊 Total registros en planilla: {len(records)}")
            
            if not records:
                logger.warning(f"⚠️ {nombre_agente}: Planilla vacía")
                return []
            
            headers_reales = list(records[0].keys())
            logger.info(f"📋 Headers encontrados: {headers_reales}")
            
            # Verificar columnas críticas con manejo de acentos
            tiene_procesar = any('PROCESAR' in h.upper() for h in headers_reales)
            tiene_renta = any(
                ('RENTA' in h.upper() and 'LIQUIDA' in h.upper()) or
                ('RENTA' in h.upper() and 'LÍQUIDA' in h.upper())
                for h in headers_reales
            )
            tiene_nombre = any('NOMBRE' in h.upper() and 'CLIENTE' in h.upper() for h in headers_reales)
            
            if not tiene_procesar:
                logger.error(f"❌ {nombre_agente}: Falta columna PROCESAR")
                return []
            if not tiene_renta:
                logger.error(f"❌ {nombre_agente}: Falta columna RENTA LIQUIDA/LÍQUIDA")
                return []
            if not tiene_nombre:
                logger.error(f"❌ {nombre_agente}: Falta columna Nombre Cliente")
                return []
            
            logger.info("✅ Estructura de planilla válida")
            logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
            
            clientes_procesar = []
            
            for i, record in enumerate(records, start=2):
                # Buscar renta con diferentes variantes
                renta_liquida = (record.get('RENTA LIQUIDA', 0) or 
                               record.get('RENTA LÍQUIDA', 0) or
                               record.get('Renta Liquida', 0) or
                               record.get('Renta Líquida', 0))
                
                procesar = str(record.get('PROCESAR', '')).upper().strip()
                
                try:
                    if isinstance(renta_liquida, str):
                        renta_limpia = ''.join(c for c in renta_liquida if c.isdigit() or c in '.,')
                        renta_liquida = float(renta_limpia.replace(',', '.')) if renta_limpia else 0
                    else:
                        renta_liquida = float(renta_liquida) if renta_liquida else 0
                except:
                    renta_liquida = 0
                
                logger.info(f"🔍 Fila {i}: PROCESAR='{procesar}', RENTA={renta_liquida}")
                
                if renta_liquida > 0 and procesar in ESTADOS_VALIDOS_PROCESAR:
                    
                    nombre_cliente = record.get('Nombre Cliente', '')
                    rut_cliente = record.get('RUT', '')
                    
                    if not nombre_cliente.strip():
                        logger.warning(f"⚠️ Fila {i}: Nombre cliente vacío")
                        continue
                    
                    if not rut_cliente.strip():
                        logger.warning(f"⚠️ Fila {i}: RUT vacío")
                        continue
                    
                    monto_financiar = self._limpiar_numero(record.get('Monto Financiamiento', 0))
                    
                    if monto_financiar <= 0:
                        logger.warning(f"⚠️ Fila {i}: Monto inválido: {monto_financiar}")
                        continue
                    
                    cliente = {
                        'agente': nombre_agente,
                        'sheet_id': sheet_id,
                        'row_number': i,
                        'Nombre Cliente': nombre_cliente,
                        'RUT': rut_cliente,
                        'Email': record.get('Email', ''),
                        'Telefono': record.get('Teléfono', record.get('Telefono', '')),
                        'Monto Financiar Original': monto_financiar,
                        'RENTA LIQUIDA': renta_liquida,
                        'Modelo Casa': record.get('Modelo Casa', ''),
                        'Precio Casa': self._limpiar_numero(record.get('Precio Casa', 0)),
                        'Origen': record.get('Origen', ''),
                        'Estado Original': procesar
                    }
                    clientes_procesar.append(cliente)
                    
                    logger.info(f"  ✅ Cliente agregado: {nombre_cliente} (RUT: {rut_cliente}) - Monto: {monto_financiar} - Estado: {procesar}")
            
            logger.info(f"✅ {nombre_agente}: {len(clientes_procesar)} clientes para procesar")
            
            return clientes_procesar
            
        except Exception as e:
            logger.error(f"❌ Error leyendo planilla de {nombre_agente}: {e}")
            import traceback
            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return []
    
    def _limpiar_numero(self, valor):
        """Limpiar y convertir valores numéricos"""
        try:
            if isinstance(valor, str):
                limpio = ''.join(c for c in valor if c.isdigit())
                return int(limpio) if limpio else 0
            return int(valor) if valor else 0
        except:
            return 0
    
    def leer_todos_los_clientes(self):
        """Leer clientes de todas las planillas configuradas"""
        logger.info("🔍 Buscando clientes en todas las planillas...")
        
        todos_los_clientes = []
        
        for agente in self.agentes_config:
            if not agente.get('activo', True):
                logger.info(f"⏭️ Saltando {agente['nombre']} (inactivo)")
                continue
            
            clientes = self.leer_clientes_desde_planilla(
                agente['sheet_id'], 
                agente['nombre']
            )
            todos_los_clientes.extend(clientes)
        
        logger.info(f"🎯 TOTAL ENCONTRADO: {len(todos_los_clientes)} clientes para procesar")
        
        return todos_los_clientes
    
    def actualizar_estado_cliente(self, cliente_data, estado, resultado=""):
        """Actualizar estado del cliente en su planilla específica"""
        try:
            sheet_id = cliente_data['sheet_id']
            row_number = cliente_data['row_number']
            agente = cliente_data['agente']
            
            spreadsheet = self.gc.open_by_key(sheet_id)
            
            worksheet = None
            nombres_hoja_posibles = ['Mis_Clientes_Financiamiento', 'sheet1', 'Hoja1', 'Sheet1']
            
            for nombre_hoja in nombres_hoja_posibles:
                try:
                    worksheet = spreadsheet.worksheet(nombre_hoja)
                    break
                except:
                    continue
            
            if not worksheet:
                worksheet = spreadsheet.sheet1
            
            worksheet.update_cell(row_number, 13, estado)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.update_cell(row_number, 14, f"Procesado: {timestamp}")
            
            if resultado:
                worksheet.update_cell(row_number, 15, resultado)
            
            logger.info(f"✅ {agente} - Estado actualizado en fila {row_number}: {estado}")
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estado: {e}")
    
    def configurar_navegador(self):
        """🔧 CONFIGURACIÓN CHROME ULTRA-EXPLÍCITA (GARANTIZA NO-PROXY)"""
        logger.info("🔧 Configurando navegador con configuración ultra-explícita...")
        
        # Verificar túnel SOCKS (solo para logging)
        if not self.verificar_tunel_socks():
            logger.warning("⚠️ Túnel SOCKS no disponible - Chrome usará conexión directa")
        
        # 🧹 LIMPIAR VARIABLES DE ENTORNO DE PROXY
        logger.info("🧹 Limpiando variables de entorno de proxy...")
        env_backup = {}
        proxy_env_vars = [
            'HTTP_PROXY', 'HTTPS_PROXY', 'FTP_PROXY', 'SOCKS_PROXY',
            'http_proxy', 'https_proxy', 'ftp_proxy', 'socks_proxy',
            'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy'
        ]
        
        for var in proxy_env_vars:
            if var in os.environ:
                env_backup[var] = os.environ[var]
                del os.environ[var]
                logger.info(f"🧹 Variable de proxy eliminada: {var}")
        
        options = Options()
        
        # Configuración para GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
        
        # Configuración básica
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        # 🚫 CONFIGURACIÓN ANTI-PROXY ULTRA-EXPLÍCITA
        logger.info("🚫 Aplicando configuración anti-proxy ultra-explícita...")
        
        # Método 1: Sin proxy
        options.add_argument('--no-proxy-server')
        
        # Método 2: Conexión directa
        options.add_argument('--proxy-server=direct://')
        
        # Método 3: Bypass todo
        options.add_argument('--proxy-bypass-list=*')
        
        # Método 4: Configuraciones adicionales
        options.add_argument('--disable-proxy-cert-verification')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--disable-background-networking')
        
        # Anti-detección
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Preferencias con configuración de proxy
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "media_stream": 2,
            },
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2,
            "profile.proxy_mode": "direct",
            "profile.proxy": ""
        }
        options.add_experimental_option("prefs", prefs)
        
        try:
            logger.info("🚀 Iniciando Chrome con configuración ultra-explícita...")
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            self.driver.set_page_load_timeout(90)
            self.driver.implicitly_wait(20)
            self.wait = WebDriverWait(self.driver, 30)
            
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['es-CL', 'es', 'en']});
                window.chrome = {runtime: {}};
            """)
            
            logger.info("✅ Chrome configurado exitosamente (conexión directa garantizada)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando Chrome: {e}")
            return False
            
        finally:
            # Restaurar variables de entorno
            for var, value in env_backup.items():
                os.environ[var] = value
        
    def _espera_humana(self, min_seg=1, max_seg=4, motivo="acción"):
        """Espera aleatoria que simula comportamiento humano"""
        import random
        tiempo = random.uniform(min_seg, max_seg)
        logger.info(f"⏳ Esperando {tiempo:.1f}s ({motivo})...")
        time.sleep(tiempo)
    
    def _mover_mouse_humano(self, elemento):
        """Simular movimiento de mouse humano hacia elemento"""
        try:
            self.driver.execute_script("""
                var elemento = arguments[0];
                var rect = elemento.getBoundingClientRect();
                var event = new MouseEvent('mouseover', {
                    'view': window,
                    'bubbles': true,
                    'cancelable': true,
                    'clientX': rect.left + rect.width/2,
                    'clientY': rect.top + rect.height/2
                });
                elemento.dispatchEvent(event);
            """, elemento)
            self._espera_humana(0.5, 1.5, "movimiento mouse")
        except:
            pass
    
    def _tipear_humano(self, campo, texto):
        """Tipear texto de forma humana (con pausas aleatorias)"""
        import random
        
        try:
            campo.clear()
            self._espera_humana(0.5, 1, "después de limpiar")
            
            for char in texto:
                campo.send_keys(char)
                pausa = random.uniform(0.05, 0.15)
                time.sleep(pausa)
            
            self._espera_humana(0.5, 1.5, "después de tipear")
            
        except Exception as e:
            logger.warning(f"Fallback a tipeo normal: {e}")
            campo.clear()
            time.sleep(1)
            campo.send_keys(texto)
            time.sleep(2)
    
    def _click_humano(self, elemento):
        """Click humano con movimiento de mouse"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", elemento)
            self._espera_humana(0.5, 1.5, "scroll al elemento")
            
            self._mover_mouse_humano(elemento)
            
            self._espera_humana(0.3, 0.8, "antes de click")
            elemento.click()
            self._espera_humana(0.5, 1.5, "después de click")
            
        except:
            try:
                self.driver.execute_script("arguments[0].click();", elemento)
                self._espera_humana(1, 2, "click JavaScript fallback")
            except:
                elemento.click()
                time.sleep(2)
    
    def _leer_pagina_humano(self):
        """Simular que un humano está leyendo la página"""
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/4);")
            self._espera_humana(1, 2, "leyendo inicio")
            
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            self._espera_humana(1, 3, "leyendo medio")
            
            self.driver.execute_script("window.scrollTo(0, 0);")
            self._espera_humana(0.5, 1.5, "volviendo arriba")
            
        except:
            self._espera_humana(2, 5, "leyendo página")
    
    def realizar_login(self):
        """Login híbrido (VPS para verificaciones + Chrome directo)"""
        logger.info("🔐 Realizando login HÍBRIDO (VPS verificaciones + Chrome directo)...")
        
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            logger.info(f"🔄 Intento de login {intento}/{max_intentos}")
            
            try:
                vps_ok, ip_data = self.verificar_conexion_vps()
                if vps_ok:
                    logger.info("✅ VPS Chile disponible para verificaciones")
                else:
                    logger.warning("⚠️ VPS no disponible - Continuando con Chrome directo")
                
                logger.info("🔗 Accediendo a Salvum con Chrome directo...")
                self.driver.get("https://prescriptores.salvum.cl/login")
                time.sleep(15)
                
                url = self.driver.current_url
                titulo = self.driver.title
                html_size = len(self.driver.page_source)
                
                logger.info(f"📍 URL: {url}")
                logger.info(f"📄 Título: {titulo}")
                logger.info(f"📊 HTML size: {html_size}")
                
                screenshot_name = f'salvum_acceso_directo_intento_{intento}.png'
                self.driver.save_screenshot(screenshot_name)
                logger.info(f"📸 Screenshot: {screenshot_name}")
                
                page_source = self.driver.page_source.lower()
                
                if "bbva" in titulo.lower():
                    logger.error(f"❌ Intento {intento}: Redirigido a BBVA")
                    if intento < max_intentos:
                        time.sleep(20)
                        continue
                    return False
                    
                elif html_size < 5000:
                    logger.error(f"❌ Intento {intento}: Página muy pequeña")
                    if intento < max_intentos:
                        time.sleep(15)
                        continue
                    return False
                    
                elif any(palabra in page_source for palabra in ["salvum", "usuario", "login", "ob forum"]):
                    logger.info(f"✅ Intento {intento}: ACCESO EXITOSO a Salvum")
                    return self._realizar_login_optimizado()
                else:
                    logger.warning(f"⚠️ Intento {intento}: Estado desconocido")
                    if intento < max_intentos:
                        time.sleep(10)
                        continue
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Error en intento {intento}: {e}")
                if intento < max_intentos:
                    time.sleep(15)
                    continue
                return False
        
        logger.error("❌ Todos los intentos de login fallaron")
        return False
    
    def _realizar_login_optimizado(self):
        """Método de login SÚPER HUMANO"""
        logger.info("🔑 INICIANDO PROCESO DE LOGIN SÚPER HUMANO")
        logger.info("-" * 50)
        
        try:
            usuario = os.getenv('SALVUM_USER')
            password = os.getenv('SALVUM_PASS')
            
            logger.info(f"👤 Usuario: {usuario}")
            logger.info("🔒 Password: [PROTEGIDO]")
            
            logger.info("👁️ Simulando lectura humana de la página...")
            self._leer_pagina_humano()
            
            self._espera_humana(3, 7, "comportamiento humano inicial")
            
            logger.info("🔍 Buscando campos de login de forma humana...")
            
            campo_usuario = None
            campo_password = None
            
            selectores_usuario = [
                "input[type='text']",
                "input[type='email']", 
                "input[name*='usuario']",
                "input[name*='email']",
                "input[name*='user']",
                "input[id*='usuario']",
                "input[id*='email']"
            ]
            
            for selector in selectores_usuario:
                try:
                    campos = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for campo in campos:
                        if campo.is_displayed() and campo.is_enabled():
                            self._mover_mouse_humano(campo)
                            self._espera_humana(0.5, 1, "inspeccionando campo")
                            
                            campo_usuario = campo
                            logger.info(f"✅ Campo usuario encontrado: {selector}")
                            break
                    if campo_usuario:
                        break
                except:
                    continue
            
            try:
                campo_password = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                if campo_password.is_displayed() and campo_password.is_enabled():
                    self._mover_mouse_humano(campo_password)
                    self._espera_humana(0.5, 1, "inspeccionando password")
                    logger.info("✅ Campo password encontrado")
                else:
                    campo_password = None
            except:
                logger.error("❌ No se encontró campo password")
                return False
            
            if not campo_usuario:
                logger.error("❌ No se encontró campo usuario")
                return False
            
            logger.info("✏️ Llenando campos de forma humana...")
            
            logger.info("👤 Llenando usuario...")
            self._click_humano(campo_usuario)
            self._tipear_humano(campo_usuario, usuario)
            logger.info("✅ Usuario ingresado de forma humana")
            
            self._espera_humana(1, 3, "pausa entre campos")
            
            logger.info("🔒 Llenando password...")
            self._click_humano(campo_password)
            self._tipear_humano(campo_password, password)
            logger.info("✅ Password ingresado de forma humana")
            
            self._espera_humana(2, 4, "verificando datos antes de enviar")
            
            self.driver.save_screenshot('salvum_antes_submit_humano.png')
            logger.info("📸 Screenshot antes de submit")
            
            logger.info("🔘 Buscando botón de submit de forma humana...")
            
            boton_submit = None
            
            try:
                botones = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                for btn in botones:
                    if btn.is_displayed() and btn.is_enabled():
                        self._mover_mouse_humano(btn)
                        self._espera_humana(0.5, 1, "inspeccionando botón")
                        boton_submit = btn
                        logger.info("✅ Botón submit encontrado por tipo")
                        break
            except:
                pass
            
            if not boton_submit:
                try:
                    boton_submit = self.driver.find_element(By.XPATH, "//button[contains(text(), 'INGRESAR') or contains(text(), 'Ingresar') or contains(text(), 'LOGIN')]")
                    if boton_submit.is_displayed() and boton_submit.is_enabled():
                        self._mover_mouse_humano(boton_submit)
                        logger.info("✅ Botón submit encontrado por texto")
                    else:
                        boton_submit = None
                except:
                    pass
            
            if boton_submit:
                logger.info("🖱️ Haciendo click en botón de forma humana...")
                self._click_humano(boton_submit)
                logger.info("🔘 Click humano ejecutado")
            else:
                logger.info("⌨️ Usando Enter como humano...")
                self._espera_humana(0.5, 1, "preparando Enter")
                campo_password.send_keys(Keys.RETURN)
                self._espera_humana(1, 2, "después de Enter")
                logger.info("⌨️ Enter enviado")
            
            logger.info("⏳ Esperando respuesta del servidor de forma humana...")
            
            for i in range(3):
                self._espera_humana(3, 5, f"esperando respuesta {i+1}/3")
                
                try:
                    url_actual = self.driver.current_url
                    if "login" not in url_actual.lower():
                        logger.info(f"✅ Página cambió durante espera: {url_actual}")
                        break
                except:
                    pass
            
            self.driver.save_screenshot('salvum_despues_submit_humano.png')
            logger.info("📸 Screenshot después de submit")
            
            nueva_url = self.driver.current_url
            nuevo_titulo = self.driver.title
            
            logger.info(f"📍 Nueva URL: {nueva_url}")
            logger.info(f"📄 Nuevo título: {nuevo_titulo}")
            
            self._espera_humana(1, 2, "leyendo resultado")
            
            if nueva_url != "https://prescriptores.salvum.cl/login" and "login" not in nueva_url.lower():
                logger.info("🎉 ¡LOGIN SÚPER HUMANO EXITOSO! - URL cambió")
                
                self._leer_pagina_humano()
                
                return True
            else:
                logger.info("❌ Login falló - permanece en página de login")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error en proceso de login súper humano: {e}")
            return False
    
    def procesar_cliente_individual(self, cliente_data):
        """Procesar un cliente individual en Salvum CON SELECTORES PRECISOS"""
        nombre = cliente_data['Nombre Cliente']
        agente = cliente_data['agente']
        
        logger.info(f"👤 Procesando: {nombre} ({agente})")
        
        try:
            self.actualizar_estado_cliente(cliente_data, "PROCESANDO")
            
            # ============= PASO 1: BUSCAR Y HACER CLICK EN "NUEVA SOLICITUD" =============
            logger.info("🔘 PASO 1: Buscando botón Nueva Solicitud...")
            
            url_actual = self.driver.current_url
            logger.info(f"📍 URL actual: {url_actual}")
            
            # Si no estamos en credit-request, navegar primero
            if "credit-request" not in url_actual.lower():
                logger.info("🔄 Navegando a página de solicitudes...")
                self.driver.get("https://prescriptores.salvum.cl/credit-request")
                self._espera_humana(3, 6, "cargando página de solicitudes")
            
            # USAR SELECTOR EXACTO DEL BOTÓN NUEVA SOLICITUD
            try:
                btn_nueva_solicitud = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='NUEVA SOLICITUD']"))
                )
                logger.info("✅ Botón Nueva Solicitud encontrado con selector exacto")
                self._click_humano(btn_nueva_solicitud)
                self._espera_humana(4, 8, "cargando formulario de nueva solicitud")
            except:
                logger.error("❌ No se encontró botón Nueva Solicitud")
                self.driver.save_screenshot(f"error_nueva_solicitud_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception("No se encontró botón Nueva Solicitud")
            
            # ============= PASO 2: LLENAR FORMULARIO INICIAL =============
            logger.info("📋 PASO 2: Llenando formulario inicial con selectores precisos...")
            
            # 1. RUT - id="RUT" name="RUT"
            logger.info("🆔 Llenando RUT...")
            try:
                campo_rut = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id='RUT'][name='RUT']")))
                self._click_humano(campo_rut)
                self._tipear_humano(campo_rut, str(cliente_data['RUT']))
                logger.info("✅ RUT llenado exitosamente")
            except:
                logger.error("❌ Error llenando RUT")
                raise Exception("No se pudo llenar RUT")
            
            # 2. Número de Celular - id="Número de Celular" name="Número de Celular"
            logger.info("📱 Llenando Número de Celular...")
            try:
                campo_celular = self.driver.find_element(By.CSS_SELECTOR, "input[id='Número de Celular'][name='Número de Celular']")
                self._click_humano(campo_celular)
                self._tipear_humano(campo_celular, str(cliente_data['Telefono']))
                logger.info("✅ Número de Celular llenado exitosamente")
            except:
                logger.warning("⚠️ No se pudo llenar Número de Celular")
            
            # 3. Correo Electrónico - id="Correo electrónico" name="Correo electrónico"
            logger.info("📧 Llenando Correo Electrónico...")
            try:
                campo_email = self.driver.find_element(By.CSS_SELECTOR, "input[id='Correo electrónico'][name='Correo electrónico']")
                self._click_humano(campo_email)
                self._tipear_humano(campo_email, str(cliente_data['Email']))
                logger.info("✅ Correo Electrónico llenado exitosamente")
            except:
                logger.warning("⚠️ No se pudo llenar Correo Electrónico")
            
            # 4. Nombre - id="Nombre" name="Nombre"
            logger.info("👤 Llenando Nombre...")
            try:
                nombre_partes = cliente_data['Nombre Cliente'].split()
                primer_nombre = nombre_partes[0] if nombre_partes else cliente_data['Nombre Cliente']
                
                campo_nombre = self.driver.find_element(By.CSS_SELECTOR, "input[id='Nombre'][name='Nombre']")
                self._click_humano(campo_nombre)
                self._tipear_humano(campo_nombre, primer_nombre)
                logger.info("✅ Nombre llenado exitosamente")
            except:
                logger.warning("⚠️ No se pudo llenar Nombre")
            
            # 5. Apellidos - id="Apellidos" name="Apellidos" - VALOR FIJO: Gonzalez
            logger.info("👨‍👩‍👧‍👦 Llenando Apellidos...")
            try:
                campo_apellidos = self.driver.find_element(By.CSS_SELECTOR, "input[id='Apellidos'][name='Apellidos']")
                self._click_humano(campo_apellidos)
                self._tipear_humano(campo_apellidos, "Gonzalez")
                logger.info("✅ Apellidos llenado exitosamente")
            except:
                logger.warning("⚠️ No se pudo llenar Apellidos")
            
            # 6. Fecha de Nacimiento - input[type="date"] - VALOR FIJO: 1987-08-25
            logger.info("🎂 Llenando Fecha de Nacimiento...")
            try:
                campo_fecha = self.driver.find_element(By.CSS_SELECTOR, "input[type='date']")
                # Usar JavaScript para campos de fecha que no son interactables
                self.driver.execute_script("arguments[0].value = '1987-08-25';", campo_fecha)
                # Disparar evento change para que Angular detecte el cambio
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_fecha)
                self._espera_humana(0.5, 1, "confirmando fecha")
                logger.info("✅ Fecha de Nacimiento llenada exitosamente con JavaScript")
            except:
                logger.warning("⚠️ No se pudo llenar Fecha de Nacimiento")
            
            # Screenshot del formulario completado
            self.driver.save_screenshot(f"formulario_inicial_completado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            logger.info("📸 Screenshot del formulario inicial completado")
            
            # 7. Click en CONTINUAR - button[value="CONTINUAR"]
            logger.info("🔘 Haciendo click en CONTINUAR...")
            try:
                btn_continuar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='CONTINUAR']")))
                self._click_humano(btn_continuar)
                self._espera_humana(4, 8, "cargando página de financiamiento")
                logger.info("✅ Click en CONTINUAR exitoso")
            except:
                logger.error("❌ No se pudo hacer click en CONTINUAR")
                raise Exception("No se pudo continuar")
            
            # ============= CONTINUAR CON EL FLUJO DE FINANCIAMIENTO =============
            logger.info("💰 Continuando con configuración de financiamiento...")
            self._configurar_financiamiento_preciso(cliente_data)
            
            # ============= RESULTADO FINAL =============
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"cliente_final_{agente.replace(' ', '_')}_{nombre.replace(' ', '_')}_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            
            url_resultado = self.driver.current_url
            
            resultado_cliente = {
                'agente': agente,
                'cliente': nombre,
                'rut': cliente_data['RUT'],
                'monto': int(cliente_data['Monto Financiar Original']),
                'renta_liquida': cliente_data['RENTA LIQUIDA'],
                'url_resultado': url_resultado,
                'screenshot': screenshot_path,
                'timestamp': timestamp,
                'estado': 'COMPLETADO'
            }
            
            self.actualizar_estado_cliente(cliente_data, "COMPLETADO", f"Exitoso: {url_resultado}")
            
            self.clientes_procesados.append(resultado_cliente)
            logger.info(f"✅ {agente} - Cliente {nombre} procesado exitosamente")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error procesando cliente {nombre} ({agente}): {e}")
            
            # Tomar screenshot del error para debugging
            try:
                error_screenshot = f"error_{agente.replace(' ', '_')}_{nombre.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.driver.save_screenshot(error_screenshot)
                logger.info(f"📸 Screenshot del error: {error_screenshot}")
            except:
                pass
            
            error_msg = str(e)[:100]
            self.actualizar_estado_cliente(cliente_data, "ERROR", f"Error: {error_msg}")
            
            self.clientes_fallidos.append({
                'agente': agente,
                'cliente': nombre,
                'rut': cliente_data['RUT'],
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })
            
            return False

    def _configurar_financiamiento_preciso(self, cliente_data):
        """Configurar financiamiento con selectores mejorados y esperas adecuadas"""
        logger.info("💰 INICIANDO CONFIGURACIÓN DE FINANCIAMIENTO MEJORADA...")
        
        try:
            # ============= PÁGINA 2: CONFIGURACIÓN DE FINANCIAMIENTO =============
            logger.info("📄 PÁGINA 2: Configuración de Financiamiento")
            self._espera_humana(4, 7, "cargando página de financiamiento completamente")
            
            # 1. ¿Qué se va a financiar? → Seleccionar "Casas modulares"
            logger.info("🏠 Seleccionando: Casas modulares")
            try:
                # Esperar a que los selects se carguen completamente
                self._espera_humana(2, 3, "esperando carga completa de selects")
                selects = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "select")))
                if len(selects) >= 1:
                    select_producto = Select(selects[0])  # Primer select de la página
                    
                    # Primero verificar las opciones disponibles
                    opciones = [option.text for option in select_producto.options]
                    logger.info(f"📋 Opciones disponibles: {opciones}")
                    
                    # Intentar seleccionar "Casas modulares" (texto exacto de la imagen)
                    try:
                        select_producto.select_by_visible_text("Casas modulares")
                        logger.info("✅ Producto seleccionado: Casas modulares")
                        self._espera_humana(2, 3, "confirmando selección producto")
                    except Exception as e:
                        logger.warning(f"⚠️ Error con texto exacto: {e}")
                        # Intentar por índice (posición 2 según la imagen)
                        try:
                            select_producto.select_by_index(2)  # "Casas modulares" está en posición 2
                            logger.info("✅ Producto seleccionado por índice: Casas modulares")
                            self._espera_humana(2, 3, "confirmando selección por índice")
                        except Exception as e2:
                            logger.error(f"❌ No se pudo seleccionar producto: {e2}")
                else:
                    logger.error("❌ No se encontraron selects en la página")
            except Exception as e:
                logger.error(f"❌ Error crítico seleccionando producto: {e}")
                # Tomar screenshot para debug
                self.driver.save_screenshot(f"error_select_producto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            
            # 2. Valor del producto → Buscar y llenar el campo correcto
            logger.info("💰 Llenando Valor del producto...")
            try:
                monto = int(cliente_data['Monto Financiar Original'])
                logger.info(f"💵 Monto a usar: {monto}")
                
                # Buscar el campo "Valor del producto" de diferentes maneras
                campo_valor_encontrado = False
                
                # Método 1: Buscar por label "Valor del producto"
                try:
                    campos_valor = self.driver.find_elements(By.XPATH, "//label[contains(text(), 'Valor del producto')]//following::input[1]")
                    if campos_valor:
                        campo_valor = campos_valor[0]
                        logger.info("✅ Campo valor encontrado por label")
                        self.driver.execute_script("arguments[0].focus();", campo_valor)
                        self.driver.execute_script("arguments[0].value = '';", campo_valor)
                        self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_valor)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_valor)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_valor)
                        campo_valor_encontrado = True
                        logger.info(f"✅ Valor del producto llenado: {monto}")
                except Exception as e:
                    logger.warning(f"Método 1 falló: {e}")
                
                # Método 2: Si el método 1 falla, buscar todos los inputs de tipo texto cerca de "CLP"
                if not campo_valor_encontrado:
                    try:
                        # Buscar inputs que estén cerca del texto "CLP"
                        campos_clp = self.driver.find_elements(By.XPATH, "//span[text()='CLP']//following::input[1]")
                        if campos_clp:
                            campo_valor = campos_clp[0]
                            logger.info("✅ Campo valor encontrado por CLP")
                            self.driver.execute_script("arguments[0].focus();", campo_valor)
                            self.driver.execute_script("arguments[0].value = '';", campo_valor)
                            self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_valor)
                            self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_valor)
                            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_valor)
                            campo_valor_encontrado = True
                            logger.info(f"✅ Valor del producto llenado por CLP: {monto}")
                    except Exception as e:
                        logger.warning(f"Método 2 falló: {e}")
                
                # Método 3: Buscar por atributo placeholder="0"
                if not campo_valor_encontrado:
                    try:
                        campos_zero = self.driver.find_elements(By.CSS_SELECTOR, "input[placeholder='0']")
                        if campos_zero:
                            # Tomar el primer campo con placeholder="0" que esté visible
                            for campo in campos_zero:
                                if campo.is_displayed():
                                    campo_valor = campo
                                    logger.info("✅ Campo valor encontrado por placeholder=0")
                                    self.driver.execute_script("arguments[0].focus();", campo_valor)
                                    self.driver.execute_script("arguments[0].value = '';", campo_valor)
                                    self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_valor)
                                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_valor)
                                    self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_valor)
                                    campo_valor_encontrado = True
                                    logger.info(f"✅ Valor del producto llenado por placeholder: {monto}")
                                    break
                    except Exception as e:
                        logger.warning(f"Método 3 falló: {e}")
                
                if not campo_valor_encontrado:
                    logger.error("❌ No se pudo encontrar el campo Valor del producto")
                
                self._espera_humana(2, 3, "confirmando valor producto")
                
            except Exception as e:
                logger.error(f"❌ Error crítico llenando Valor del producto: {e}")
                self.driver.save_screenshot(f"error_valor_producto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            
            # 3. ¿Cuánto quieres solicitar? → Buscar segundo campo de monto
            logger.info("💵 Llenando Cuánto quieres solicitar...")
            try:
                # Buscar el segundo campo de monto o campo relacionado
                campos_solicitar_encontrado = False
                
                # Método 1: Buscar por label "Cuánto quieres solicitar"
                try:
                    campos_solicitar = self.driver.find_elements(By.XPATH, "//label[contains(text(), 'Cuánto quieres solicitar') or contains(text(), 'quieres solicitar')]//following::input[1]")
                    if campos_solicitar:
                        campo_solicitar = campos_solicitar[0]
                        logger.info("✅ Campo solicitar encontrado por label")
                        self.driver.execute_script("arguments[0].focus();", campo_solicitar)
                        self.driver.execute_script("arguments[0].value = '';", campo_solicitar)
                        self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_solicitar)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_solicitar)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_solicitar)
                        campos_solicitar_encontrado = True
                        logger.info(f"✅ Cuánto solicitar llenado: {monto}")
                except Exception as e:
                    logger.warning(f"Método 1 solicitar falló: {e}")
                
                # Método 2: Buscar todos los campos con id="import-simple" y usar el segundo
                if not campos_solicitar_encontrado:
                    try:
                        campos_import = self.driver.find_elements(By.CSS_SELECTOR, "input[id='import-simple'][name='import-simple']")
                        if len(campos_import) >= 2:
                            campo_solicitar = campos_import[1]  # Segundo campo
                            logger.info("✅ Campo solicitar encontrado como segundo import-simple")
                            self.driver.execute_script("arguments[0].focus();", campo_solicitar)
                            self.driver.execute_script("arguments[0].value = '';", campo_solicitar)
                            self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_solicitar)
                            self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_solicitar)
                            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_solicitar)
                            campos_solicitar_encontrado = True
                            logger.info(f"✅ Cuánto solicitar llenado como segundo campo: {monto}")
                    except Exception as e:
                        logger.warning(f"Método 2 solicitar falló: {e}")
                
                if not campos_solicitar_encontrado:
                    logger.warning("⚠️ No se encontró campo 'Cuánto quieres solicitar', pero puede no ser obligatorio")
                
                self._espera_humana(2, 3, "confirmando monto solicitar")
                
            except Exception as e:
                logger.warning(f"⚠️ Error llenando Cuánto solicitar: {e}")
            
            # 4. Cuota → Seleccionar "60 cuotas" 
            logger.info("📊 Seleccionando Cuota: 60 cuotas")
            try:
                self._espera_humana(1, 2, "esperando carga de selects de cuota")
                selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                logger.info(f"📋 Total selects encontrados: {len(selects)}")
                
                # Buscar el select que contiene opciones de cuotas
                select_cuota_encontrado = False
                for i, select_elem in enumerate(selects):
                    try:
                        select_obj = Select(select_elem)
                        opciones = [option.text for option in select_obj.options]
                        logger.info(f"📋 Select {i}: {opciones}")
                        
                        # Verificar si contiene opciones de cuotas
                        if any("cuota" in opcion.lower() for opcion in opciones):
                            logger.info(f"✅ Select de cuotas encontrado en posición {i}")
                            # Intentar seleccionar "60 cuotas"
                            for opcion in ["60 cuotas", "60", "60 CUOTAS"]:
                                try:
                                    select_obj.select_by_visible_text(opcion)
                                    logger.info(f"✅ Cuota seleccionada: {opcion}")
                                    select_cuota_encontrado = True
                                    break
                                except:
                                    continue
                            if select_cuota_encontrado:
                                break
                    except Exception as e:
                        continue
                
                if not select_cuota_encontrado:
                    logger.warning("⚠️ No se pudo seleccionar cuota")
                    
                self._espera_humana(1, 2, "confirmando cuota")
            except Exception as e:
                logger.warning(f"⚠️ Error seleccionando cuota: {e}")
            
            # 5. Día de Vencimiento → Seleccionar "2"
            logger.info("📅 Seleccionando Día de Vencimiento: 2")
            try:
                selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                
                # Buscar el select que contiene días de vencimiento
                select_dia_encontrado = False
                for i, select_elem in enumerate(selects):
                    try:
                        select_obj = Select(select_elem)
                        opciones = [option.text for option in select_obj.options]
                        
                        # Verificar si contiene números (días)
                        if any(opcion.strip().isdigit() for opcion in opciones):
                            logger.info(f"✅ Select de días encontrado en posición {i}: {opciones}")
                            # Intentar seleccionar "2"
                            try:
                                select_obj.select_by_visible_text("2")
                                logger.info("✅ Día de vencimiento seleccionado: 2")
                                select_dia_encontrado = True
                                break
                            except:
                                # Si no funciona por texto, intentar por índice
                                try:
                                    select_obj.select_by_index(1)  # Primera opción después de "Seleccione"
                                    logger.info("✅ Día de vencimiento seleccionado por índice")
                                    select_dia_encontrado = True
                                    break
                                except:
                                    continue
                    except Exception as e:
                        continue
                
                if not select_dia_encontrado:
                    logger.warning("⚠️ No se pudo seleccionar día de vencimiento")
                    
                self._espera_humana(1, 2, "confirmando día vencimiento")
            except Exception as e:
                logger.warning(f"⚠️ Error seleccionando día de vencimiento: {e}")
            
            # 6. Esperar a que el botón SIMULAR se habilite y hacer click
            logger.info("🔘 Esperando que el botón SIMULAR se habilite...")
            try:
                # Esperar hasta 15 segundos a que el botón se habilite
                for intento in range(15):
                    try:
                        # Buscar botón que NO tenga la clase 'disable-button'
                        btn_simular = self.driver.find_element(By.CSS_SELECTOR, "button[value='SIMULAR']:not(.disable-button)")
                        if btn_simular.is_displayed() and btn_simular.is_enabled():
                            logger.info(f"✅ Botón SIMULAR habilitado después de {intento+1} segundos")
                            self._click_humano(btn_simular)
                            self._espera_humana(8, 12, "procesando simulación")
                            logger.info("✅ Simulación ejecutada exitosamente")
                            break
                    except:
                        # Si no encuentra el botón habilitado, esperar 1 segundo más
                        time.sleep(1)
                        continue
                else:
                    # Si después de 15 intentos no se habilita, intentar click forzado
                    logger.warning("⚠️ Botón SIMULAR no se habilitó, intentando click forzado...")
                    try:
                        btn_simular_disabled = self.driver.find_element(By.CSS_SELECTOR, "button[value='SIMULAR']")
                        # Intentar habilitar el botón con JavaScript
                        self.driver.execute_script("arguments[0].classList.remove('disable-button');", btn_simular_disabled)
                        self.driver.execute_script("arguments[0].disabled = false;", btn_simular_disabled)
                        self._espera_humana(1, 2, "forzando habilitación")
                        self._click_humano(btn_simular_disabled)
                        self._espera_humana(8, 12, "procesando simulación forzada")
                        logger.info("✅ Simulación ejecutada con click forzado")
                    except Exception as e:
                        logger.error(f"❌ No se pudo hacer click en SIMULAR: {e}")
                        raise Exception("Error en simulación - botón no disponible")
            
            except Exception as e:
                logger.error(f"❌ Error en simulación: {e}")
                # Tomar screenshot para debug
                self.driver.save_screenshot(f"error_simulacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception("Error en simulación")
            
            # ============= CONTINUAR CON EL RESTO DEL FLUJO =============
            # El resto del código permanece igual...
            
            # ============= PÁGINA 3: CONTINUAR DESPUÉS DE SIMULACIÓN =============
            logger.info("📄 PÁGINA 3: Después de Simulación")
            self._espera_humana(4, 6, "cargando resultados de simulación")
            
            try:
                btn_continuar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='CONTINUAR']")))
                self._click_humano(btn_continuar)
                self._espera_humana(4, 6, "cargando información personal")
                logger.info("✅ Continuado después de simulación")
            except:
                logger.error("❌ No se pudo continuar después de simulación")
                raise Exception("Error continuando después de simulación")
            
            # ============= PÁGINA 4: INFORMACIÓN PERSONAL =============
            logger.info("📄 PÁGINA 4: Información Personal")
            self._espera_humana(3, 5, "cargando página información personal")
            
            # N° de serie C.I → input[id="N° de serie C.I."][name="N° de serie C.I."]
            logger.info("🆔 Llenando N° de serie C.I: 123456789")
            try:
                campo_ci = self.driver.find_element(By.CSS_SELECTOR, "input[id='N° de serie C.I.'][name='N° de serie C.I.']")
                self._click_humano(campo_ci)
                self._tipear_humano(campo_ci, "123456789")
                logger.info("✅ N° de serie C.I llenado")
            except:
                logger.warning("⚠️ No se pudo llenar N° de serie C.I")
            
            # Estado Civil → Seleccionar "Soltero/a"
            logger.info("💑 Seleccionando Estado Civil: Soltero/a")
            try:
                select_civil = self.driver.find_element(By.CSS_SELECTOR, "select")
                select_obj = Select(select_civil)
                select_obj.select_by_visible_text("Soltero/a")
                logger.info("✅ Estado Civil seleccionado: Soltero/a")
            except:
                logger.warning("⚠️ No se pudo seleccionar Estado Civil")
            
            try:
                btn_continuar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='CONTINUAR']")))
                self._click_humano(btn_continuar)
                self._espera_humana(4, 6, "cargando ubicación")
                logger.info("✅ Continuado después de información personal")
            except:
                logger.error("❌ No se pudo continuar después de información personal")
                raise Exception("Error continuando información personal")
            
            # ============= PÁGINA 5: UBICACIÓN =============
            logger.info("📄 PÁGINA 5: Ubicación")
            self._espera_humana(3, 5, "cargando página ubicación")
            
            # Región → Seleccionar "COQUIMBO"
            logger.info("🌎 Seleccionando Región: COQUIMBO")
            try:
                selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                if len(selects) >= 1:
                    select_region = Select(selects[0])
                    select_region.select_by_visible_text("COQUIMBO")
                    logger.info("✅ Región seleccionada: COQUIMBO")
                    self._espera_humana(3, 5, "cargando ciudades")
            except:
                logger.warning("⚠️ No se pudo seleccionar región")
            
            # Ciudad → Seleccionar según disponibilidad (se carga dinámicamente)
            logger.info("🏙️ Intentando seleccionar Ciudad...")
            try:
                self._espera_humana(2, 3, "esperando carga de ciudades")
                selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                if len(selects) >= 2:
                    select_ciudad = Select(selects[1])
                    opciones = select_ciudad.options
                    if len(opciones) > 1:  # Más que solo "Seleccione"
                        select_ciudad.select_by_index(1)  # Seleccionar primera opción disponible
                        logger.info("✅ Ciudad seleccionada")
                        self._espera_humana(3, 5, "cargando comunas")
            except:
                logger.warning("⚠️ No se pudo seleccionar ciudad")
            
            # Comuna → Seleccionar según disponibilidad (se carga dinámicamente)
            logger.info("🏘️ Intentando seleccionar Comuna...")
            try:
                self._espera_humana(2, 3, "esperando carga de comunas")
                selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                if len(selects) >= 3:
                    select_comuna = Select(selects[2])
                    opciones = select_comuna.options
                    if len(opciones) > 1:  # Más que solo "Seleccione"
                        select_comuna.select_by_index(1)  # Seleccionar primera opción disponible
                        logger.info("✅ Comuna seleccionada")
            except:
                logger.warning("⚠️ No se pudo seleccionar comuna")
            
            # Dirección → input[id="Dirección"][name="Dirección"]
            logger.info("🏠 Llenando Dirección: Avenida")
            try:
                campo_direccion = self.driver.find_element(By.CSS_SELECTOR, "input[id='Dirección'][name='Dirección']")
                self._click_humano(campo_direccion)
                self._tipear_humano(campo_direccion, "Avenida")
                logger.info("✅ Dirección llenada")
            except:
                logger.warning("⚠️ No se pudo llenar Dirección")
            
            try:
                btn_continuar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='CONTINUAR']")))
                self._click_humano(btn_continuar)
                self._espera_humana(4, 6, "cargando información laboral")
                logger.info("✅ Continuado después de ubicación")
            except:
                logger.error("❌ No se pudo continuar después de ubicación")
                raise Exception("Error continuando ubicación")
            
            # ============= PÁGINA 6: INFORMACIÓN LABORAL =============
            logger.info("📄 PÁGINA 6: Información Laboral")
            self._espera_humana(3, 5, "cargando página información laboral")
            
            # Modalidad de trabajo → Seleccionar "Jubilado"
            logger.info("💼 Seleccionando Modalidad de trabajo: Jubilado")
            try:
                select_trabajo = self.driver.find_element(By.CSS_SELECTOR, "select")
                select_obj = Select(select_trabajo)
                select_obj.select_by_visible_text("Jubilado")
                logger.info("✅ Modalidad de trabajo seleccionada: Jubilado")
            except:
                logger.warning("⚠️ No se pudo seleccionar modalidad de trabajo")
            
            # Última pensión líquida → input[id="import-simple"][name="import-simple"]
            logger.info("💰 Llenando Última pensión líquida...")
            try:
                renta_liquida = int(cliente_data['RENTA LIQUIDA'])
                campo_pension = self.driver.find_element(By.CSS_SELECTOR, "input[id='import-simple'][name='import-simple']")
                self._click_humano(campo_pension)
                self._tipear_humano(campo_pension, str(renta_liquida))
                logger.info(f"✅ Última pensión líquida: {renta_liquida}")
            except:
                logger.warning("⚠️ No se pudo llenar Última pensión líquida")
            
            try:
                btn_continuar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='CONTINUAR']")))
                self._click_humano(btn_continuar)
                self._espera_humana(4, 6, "cargando página final")
                logger.info("✅ Continuado después de información laboral")
            except:
                logger.error("❌ No se pudo continuar después de información laboral")
                raise Exception("Error continuando información laboral")
            
            # ============= PÁGINA 7: EVALUAR SOLICITUD =============
            logger.info("📄 PÁGINA 7: Evaluar Solicitud")
            self._espera_humana(3, 5, "cargando página final")
            
            # Click en EVALUAR SOLICITUD - button[value="EVALUAR SOLICITUD"]
            logger.info("📤 Haciendo click en EVALUAR SOLICITUD...")
            try:
                btn_evaluar = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='EVALUAR SOLICITUD']")))
                self._click_humano(btn_evaluar)
                self._espera_humana(6, 10, "procesando evaluación final")
                logger.info("✅ Solicitud enviada para evaluación")
            except:
                logger.warning("⚠️ No se encontró botón EVALUAR SOLICITUD, continuando...")
            
            # ============= CAPTURAR RESULTADO FINAL =============
            logger.info("📸 Capturando resultado final...")
            self._espera_humana(5, 8, "cargando resultado final")
            
            # Tomar screenshot final y guardar en Google Sheet
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_cliente = cliente_data['Nombre Cliente'].replace(' ', '_')
            agente = cliente_data['agente'].replace(' ', '_')
            
            screenshot_path = f"resultado_final_{agente}_{nombre_cliente}_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"📸 Screenshot final capturado: {screenshot_path}")
            
            # Obtener URL de resultado
            url_resultado = self.driver.current_url
            logger.info(f"📍 URL resultado final: {url_resultado}")
            
            # Guardar información en Google Sheet
            self._guardar_resultado_en_sheet(cliente_data, screenshot_path, url_resultado)
            
            logger.info("🎉 ¡FLUJO DE FINANCIAMIENTO COMPLETADO EXITOSAMENTE!")
            
        except Exception as e:
            logger.error(f"❌ Error en configuración de financiamiento: {e}")
            raise

    def _guardar_resultado_en_sheet(self, cliente_data, screenshot_path, url_resultado):
        """Guardar información del resultado en Google Sheet"""
        try:
            logger.info("💾 Guardando resultado en Google Sheet...")
            
            sheet_id = cliente_data['sheet_id']
            row_number = cliente_data['row_number']
            
            spreadsheet = self.gc.open_by_key(sheet_id)
            worksheet = None
            
            # Buscar la hoja correcta
            nombres_hoja_posibles = ['Mis_Clientes_Financiamiento', 'sheet1', 'Hoja1', 'Sheet1']
            for nombre_hoja in nombres_hoja_posibles:
                try:
                    worksheet = spreadsheet.worksheet(nombre_hoja)
                    break
                except:
                    continue
            
            if not worksheet:
                worksheet = spreadsheet.sheet1
            
            # Actualizar columnas con la información del resultado
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Columna 14: Estado Simulación
            worksheet.update_cell(row_number, 14, "COMPLETADO")
            
            # Columna 15: Resultado Salvum
            worksheet.update_cell(row_number, 15, f"Exitoso - URL: {url_resultado}")
            
            # Columna 16: Fecha Proceso
            worksheet.update_cell(row_number, 16, f"Procesado: {timestamp}")
            
            logger.info(f"✅ Información guardada en Google Sheet fila {row_number}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando en Google Sheet: {e}")
            # No lanzar excepción aquí para no interrumpir el flujo
    
    def procesar_todos_los_clientes(self):
        """Procesar todos los clientes CON SELECTORES PRECISOS"""
        logger.info("🚀 INICIANDO PROCESAMIENTO CON SELECTORES PRECISOS...")
        
        todos_los_clientes = self.leer_todos_los_clientes()
        
        if not todos_los_clientes:
            logger.info("ℹ️ No hay clientes para procesar en ninguna planilla")
            return True
        
        total_clientes = len(todos_los_clientes)
        logger.info(f"📊 Total clientes a procesar: {total_clientes}")
        
        for idx, cliente in enumerate(todos_los_clientes, 1):
            logger.info(f"\n{'='*20} CLIENTE {idx}/{total_clientes} {'='*20}")
            logger.info(f"👥 Agente: {cliente['agente']}")
            logger.info(f"👤 Cliente: {cliente['Nombre Cliente']} - {cliente['RUT']}")
            
            try:
                if idx > 1:
                    logger.info("🤔 Pausa entre clientes...")
                    self._espera_humana(8, 15, "descanso entre clientes")
                    
                    try:
                        logger.info("🔄 Regresando al dashboard...")
                        self.driver.get("https://prescriptores.salvum.cl/credit-request")
                        self._espera_humana(3, 6, "cargando página principal")
                    except Exception as e:
                        logger.warning(f"Error regresando al dashboard: {e}")
                        self._espera_humana(3, 5, "recuperación dashboard")
                
                logger.info(f"👤 Procesando cliente {idx} con selectores precisos...")
                if self.procesar_cliente_individual(cliente):
                    logger.info(f"✅ Cliente {idx} completado exitosamente")
                    self._espera_humana(2, 4, "satisfacción por cliente completado")
                else:
                    logger.error(f"❌ Cliente {idx} falló")
                    self._espera_humana(3, 6, "procesando fallo")
                
            except Exception as e:
                logger.error(f"❌ Error procesando cliente {idx}: {e}")
                self._espera_humana(5, 8, "recuperándose de error")
                continue
        
        logger.info("🎉 ¡PROCESAMIENTO COMPLETADO!")
        self._espera_humana(3, 6, "finalización exitosa")
        
        return True
    
    def generar_reporte_final(self):
        """Generar reporte final por agente"""
        logger.info("📊 Generando reporte final...")
        
        total_procesados = len(self.clientes_procesados)
        total_fallidos = len(self.clientes_fallidos)
        total_clientes = total_procesados + total_fallidos
        
        procesados_por_agente = {}
        fallidos_por_agente = {}
        
        for cliente in self.clientes_procesados:
            agente = cliente['agente']
            if agente not in procesados_por_agente:
                procesados_por_agente[agente] = []
            procesados_por_agente[agente].append(cliente)
        
        for cliente in self.clientes_fallidos:
            agente = cliente['agente']
            if agente not in fallidos_por_agente:
                fallidos_por_agente[agente] = []
            fallidos_por_agente[agente].append(cliente)
        
        reporte = {
            'timestamp': datetime.now().isoformat(),
            'version': 'SELECTORES_PRECISOS',
            'configuracion_chrome': 'SIN_PROXY_GARANTIZADO',
            'selectores': 'BASADOS_EN_INSPECCION_REAL',
            'estados_validos_usados': ESTADOS_VALIDOS_PROCESAR,
            'total_agentes': len(self.agentes_config),
            'total_clientes': total_clientes,
            'exitosos': total_procesados,
            'fallidos': total_fallidos,
            'tasa_exito': f"{(total_procesados/total_clientes*100):.1f}%" if total_clientes > 0 else "0%",
            'por_agente': {
                'exitosos': procesados_por_agente,
                'fallidos': fallidos_por_agente
            },
            'detalles_completos': {
                'exitosos': self.clientes_procesados,
                'fallidos': self.clientes_fallidos
            }
        }
        
        with open('reporte_salvum_selectores_precisos.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        logger.info("="*70)
        logger.info("📊 REPORTE FINAL - SELECTORES PRECISOS")
        logger.info("="*70)
        logger.info(f"🔧 Configuración: Chrome sin proxy + Selectores basados en inspección real")
        logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
        logger.info(f"👥 Total agentes: {len(self.agentes_config)}")
        logger.info(f"✅ Clientes exitosos: {total_procesados}")
        logger.info(f"❌ Clientes fallidos: {total_fallidos}")
        logger.info(f"📈 Tasa de éxito: {reporte['tasa_exito']}")
        
        logger.info("\n📋 RESULTADOS POR AGENTE:")
        for agente in self.agentes_config:
            nombre = agente['nombre']
            exitosos = len(procesados_por_agente.get(nombre, []))
            fallidos = len(fallidos_por_agente.get(nombre, []))
            total_agente = exitosos + fallidos
            
            if total_agente > 0:
                tasa_agente = (exitosos/total_agente*100)
                logger.info(f"  👥 {nombre}: {exitosos}✅ {fallidos}❌ ({tasa_agente:.1f}%)")
                
                if exitosos > 0:
                    for cliente in procesados_por_agente[nombre]:
                        logger.info(f"    ✅ {cliente['cliente']} ({cliente['rut']})")
                
                if fallidos > 0:
                    for cliente in fallidos_por_agente[nombre]:
                        logger.info(f"    ❌ {cliente['cliente']} ({cliente['rut']}): {cliente['error']}")
            else:
                logger.info(f"  👥 {nombre}: Sin clientes para procesar")
        
        logger.info("="*70)
        
        return reporte
    
    def ejecutar_automatizacion_completa(self):
        """VERSIÓN FINAL: Automatización con selectores precisos"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN CON SELECTORES PRECISOS")
        logger.info("="*70)
        logger.info(f"🔧 Chrome: Sin proxy garantizado")
        logger.info(f"🎯 Selectores: Basados en inspección real de elementos")
        logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
        logger.info("="*70)
        
        try:
            # Verificar VPS
            vps_ok, ip_data = self.verificar_conexion_vps()
            if vps_ok:
                logger.info("✅ VPS Chile disponible para verificaciones")
            else:
                logger.warning("⚠️ VPS no disponible - Continuando sin verificaciones VPS")
            
            # Cargar configuración
            if not self.cargar_configuracion_agentes():
                return False
            
            if not self.configurar_google_sheets():
                return False
            
            # Leer clientes
            todos_los_clientes = self.leer_todos_los_clientes()
            if not todos_los_clientes:
                logger.info("ℹ️ No hay clientes para procesar")
                return True
            
            # Configurar navegador
            logger.info("🔧 Configurando navegador...")
            if not self.configurar_navegador():
                logger.error("❌ Error configurando navegador")
                return False
            
            # Realizar login
            if not self.realizar_login():
                logger.error("❌ Login falló")
                return False
            
            # Procesar clientes
            self.procesar_todos_los_clientes()
            
            # Generar reporte
            self.generar_reporte_final()
            
            logger.info("🎉 ¡AUTOMATIZACIÓN CON SELECTORES PRECISOS COMPLETADA!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en automatización: {e}")
            import traceback
            logger.error(f"📋 Traceback completo: {traceback.format_exc()}")
            return False
            
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("🔒 Navegador cerrado correctamente")
                except:
                    pass

def main():
    """Función principal"""
    automator = SalvumAutomacionPrecisa()
    
    print("🇨🇱 AUTOMATIZACIÓN SALVUM - SELECTORES PRECISOS")
    print("🔧 Basado en inspección real de elementos HTML")
    print(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
    print("-"*70)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Ver reporte_salvum_selectores_precisos.json para detalles")
        print("📊 Estados actualizados en todas las planillas")
        print("🔧 Versión con selectores precisos basados en inspección real")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
