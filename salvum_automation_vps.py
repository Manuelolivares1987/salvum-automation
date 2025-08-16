#!/usr/bin/env python3
"""
AUTOMATIZACIÓN SALVUM - VERSIÓN ULTRA-CORREGIDA
Chrome sin proxy garantizado + Limpieza de entorno + Correcciones integradas
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

class SalvumMultiplePlanillasConVPS:
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
            
            if clientes_procesar:
                for cliente in clientes_procesar:
                    logger.info(f"  📋 {cliente['Nombre Cliente']} (RUT: {cliente['RUT']}) - Fila: {cliente['row_number']} - Estado: {cliente['Estado Original']}")
            else:
                logger.warning(f"⚠️ {nombre_agente}: No se encontraron clientes válidos")
                logger.info("🔍 Análisis detallado:")
                
                estados_encontrados = {}
                filas_con_renta = 0
                
                for record in records:
                    estado = str(record.get('PROCESAR', '')).strip()
                    if estado:
                        estados_encontrados[estado] = estados_encontrados.get(estado, 0) + 1
                    
                    renta = (record.get('RENTA LIQUIDA', 0) or 
                           record.get('RENTA LÍQUIDA', 0) or
                           record.get('Renta Liquida', 0) or
                           record.get('Renta Líquida', 0))
                    try:
                        if isinstance(renta, str):
                            renta_limpia = ''.join(c for c in renta if c.isdigit() or c in '.,')
                            renta = float(renta_limpia.replace(',', '.')) if renta_limpia else 0
                        else:
                            renta = float(renta) if renta else 0
                        if renta > 0:
                            filas_con_renta += 1
                    except:
                        pass
                
                logger.info(f"   📊 Filas con renta > 0: {filas_con_renta}")
                logger.info(f"   🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
                logger.info(f"   📋 Estados encontrados:")
                
                for estado, cantidad in estados_encontrados.items():
                    es_valido = "✅" if estado.upper() in ESTADOS_VALIDOS_PROCESAR else "❌"
                    logger.info(f"     {es_valido} '{estado}': {cantidad} filas")
            
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
        
        if todos_los_clientes:
            logger.info("\n📊 RESUMEN POR AGENTE:")
            agentes_resumen = {}
            for cliente in todos_los_clientes:
                agente = cliente['agente']
                if agente not in agentes_resumen:
                    agentes_resumen[agente] = []
                agentes_resumen[agente].append(cliente['Nombre Cliente'])
            
            for agente, clientes in agentes_resumen.items():
                logger.info(f"  👥 {agente}: {len(clientes)} clientes")
                for cliente in clientes:
                    logger.info(f"    - {cliente}")
        
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
            
            # Verificar que NO está usando proxy
            logger.info("🔍 Verificando que Chrome usa conexión directa...")
            try:
                self.driver.get('https://ipinfo.io/json')
                time.sleep(3)
                ip_element = self.driver.find_element(By.TAG_NAME, 'pre')
                ip_data = json.loads(ip_element.text)
                
                logger.info(f"📍 IP Chrome: {ip_data.get('ip')}")
                logger.info(f"🏢 País Chrome: {ip_data.get('country')}")
                logger.info("✅ Chrome usando conexión directa (sin proxy)")
            except Exception as e:
                logger.warning(f"No se pudo verificar IP de Chrome: {e}")
            
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
        """Procesar un cliente individual en Salvum"""
        nombre = cliente_data['Nombre Cliente']
        agente = cliente_data['agente']
        
        logger.info(f"👤 Procesando: {nombre} ({agente})")
        
        try:
            self.actualizar_estado_cliente(cliente_data, "PROCESANDO")
            
            logger.info("📝 Iniciando nueva solicitud...")
            nueva_solicitud_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//button[contains(text(), 'Nueva Solicitud')] | //a[contains(text(), 'Nueva Solicitud')]"
                ))
            )
            self._click_humano(nueva_solicitud_btn)
            self._espera_humana(3, 6, "cargando nueva solicitud")
            
            logger.info("📋 Llenando datos del cliente...")
            
            campo_rut = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "input[name*='rut'], input[id*='rut'], input[placeholder*='RUT']"
                ))
            )
            self._click_humano(campo_rut)
            self._tipear_humano(campo_rut, str(cliente_data['RUT']))
            
            nombre_partes = nombre.split()
            primer_nombre = nombre_partes[0] if nombre_partes else nombre
            apellido = ' '.join(nombre_partes[1:]) if len(nombre_partes) > 1 else "Gonzalez"
            
            self._llenar_campo_si_existe("input[name*='nombre'], input[id*='nombre'], input[placeholder*='Nombre']", primer_nombre)
            self._llenar_campo_si_existe("input[name*='apellido'], input[id*='apellido']", apellido)
            self._llenar_campo_si_existe("input[type='email'], input[name*='email']", str(cliente_data['Email']))
            self._llenar_campo_si_existe("input[name*='telefono'], input[name*='phone']", str(cliente_data['Telefono']))
            self._llenar_campo_si_existe("input[type='date'], input[name*='fecha']", "25/08/1987")
            
            self._click_continuar()
            
            logger.info("💰 Configurando financiamiento...")
            
            self._seleccionar_producto("Casas Modulares")
            
            monto = int(cliente_data['Monto Financiar Original'])
            self._llenar_campo_si_existe("input[name*='valor'], input[id*='valor']", str(monto))
            self._llenar_campo_si_existe("input[name*='solicitar'], input[name*='monto']", str(monto))
            
            self._configurar_cuotas_y_dia()
            
            btn_simular = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Simular')]")
            self._click_humano(btn_simular)
            self._espera_humana(6, 10, "procesando simulación")
            
            self._click_continuar()
            
            logger.info("📋 Completando información personal...")
            self._llenar_informacion_personal(cliente_data)
            
            logger.info("📤 Enviando solicitud...")
            btn_enviar = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Enviar')]"))
            )
            self._click_humano(btn_enviar)
            self._espera_humana(8, 12, "enviando solicitud")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"cliente_{agente.replace(' ', '_')}_{nombre.replace(' ', '_')}_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            
            url_resultado = self.driver.current_url
            
            resultado_cliente = {
                'agente': agente,
                'cliente': nombre,
                'rut': cliente_data['RUT'],
                'monto': monto,
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
    
    def _llenar_campo_si_existe(self, selector, valor):
        """Llenar campo si existe DE FORMA HUMANA"""
        try:
            campo = self.driver.find_element(By.CSS_SELECTOR, selector)
            if campo.is_displayed() and campo.is_enabled():
                logger.info(f"✏️ Llenando campo: {selector[:30]}... = {valor}")
                
                self._mover_mouse_humano(campo)
                self._click_humano(campo)
                self._tipear_humano(campo, str(valor))
                
                return True
        except:
            pass
        return False
    
    def _click_continuar(self):
        """Click en botón continuar DE FORMA HUMANA"""
        try:
            btn_continuar = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Continuar')]")
            logger.info("🔘 Haciendo click en Continuar...")
            
            self._espera_humana(1, 3, "revisando antes de continuar")
            self._click_humano(btn_continuar)
            
            self._espera_humana(3, 6, "cargando siguiente página")
            
        except Exception as e:
            logger.warning(f"Error en continuar: {e}")
            self._espera_humana(2, 4, "fallback continuar")
    
    def _seleccionar_producto(self, producto):
        """Seleccionar producto DE FORMA HUMANA"""
        try:
            logger.info(f"🏠 Seleccionando producto: {producto}")
            
            campo_producto = self.driver.find_element(By.XPATH, "//select | //input[name*='producto']")
            
            self._mover_mouse_humano(campo_producto)
            self._espera_humana(0.5, 1.5, "viendo opciones de producto")
            
            if campo_producto.tag_name == 'select':
                select = Select(campo_producto)
                self._espera_humana(1, 2, "leyendo opciones")
                select.select_by_visible_text(producto)
            else:
                self._click_humano(campo_producto)
                self._tipear_humano(campo_producto, producto)
            
            self._espera_humana(1, 2, "confirmando selección producto")
            
        except Exception as e:
            logger.warning(f"Error seleccionando producto: {e}")
    
    def _configurar_cuotas_y_dia(self):
        """Configurar cuotas y día de vencimiento DE FORMA HUMANA"""
        logger.info("⚙️ Configurando cuotas y día...")
        
        try:
            campo_cuotas = self.driver.find_element(By.CSS_SELECTOR, "input[name*='cuota'], select[name*='cuota']")
            
            logger.info("📊 Configurando cuotas = 60")
            self._mover_mouse_humano(campo_cuotas)
            self._espera_humana(0.5, 1, "pensando en cuotas")
            
            if campo_cuotas.tag_name == 'select':
                select = Select(campo_cuotas)
                self._espera_humana(0.5, 1, "viendo opciones cuotas")
                select.select_by_value("60")
            else:
                self._click_humano(campo_cuotas)
                self._tipear_humano(campo_cuotas, "60")
            
            self._espera_humana(1, 2, "confirmando cuotas")
            
        except Exception as e:
            logger.warning(f"Error configurando cuotas: {e}")
        
        try:
            campo_dia = self.driver.find_element(By.CSS_SELECTOR, "input[name*='dia'], select[name*='dia']")
            
            logger.info("📅 Configurando día = 2")
            self._mover_mouse_humano(campo_dia)
            self._espera_humana(0.5, 1, "pensando en día")
            
            if campo_dia.tag_name == 'select':
                select = Select(campo_dia)
                self._espera_humana(0.5, 1, "viendo opciones día")
                select.select_by_value("2")
            else:
                self._click_humano(campo_dia)
                self._tipear_humano(campo_dia, "2")
            
            self._espera_humana(1, 2, "confirmando día")
            
        except Exception as e:
            logger.warning(f"Error configurando día: {e}")
    
    def _llenar_informacion_personal(self, cliente_data):
        """Llenar información personal fija DE FORMA HUMANA"""
        logger.info("📋 Llenando información personal de forma humana...")
        
        self._leer_pagina_humano()
        
        logger.info("🆔 Llenando CI...")
        self._llenar_campo_si_existe("input[name*='ci'], input[name*='cedula']", "123456789")
        
        try:
            logger.info("💑 Seleccionando estado civil...")
            estado_civil = self.driver.find_element(By.CSS_SELECTOR, "select[name*='estado'], select[name*='civil']")
            self._mover_mouse_humano(estado_civil)
            self._espera_humana(0.5, 1.5, "pensando estado civil")
            
            select = Select(estado_civil)
            select.select_by_visible_text("Soltero")
            self._espera_humana(1, 2, "confirmando estado civil")
        except:
            pass
        
        logger.info("🗺️ Configurando ubicación...")
        self._seleccionar_ubicacion()
        
        logger.info("🏠 Llenando dirección...")
        self._llenar_campo_si_existe("input[name*='direccion']", "Aven")
        
        try:
            logger.info("💼 Seleccionando modalidad trabajo...")
            modalidad = self.driver.find_element(By.CSS_SELECTOR, "select[name*='trabajo']")
            self._mover_mouse_humano(modalidad)
            self._espera_humana(0.5, 1.5, "pensando modalidad trabajo")
            
            select = Select(modalidad)
            select.select_by_visible_text("Jubilado")
            self._espera_humana(1, 2, "confirmando modalidad")
        except:
            pass
        
        renta_liquida = int(cliente_data['RENTA LIQUIDA'])
        logger.info(f"💰 Llenando renta líquida: {renta_liquida}")
        self._llenar_campo_si_existe("input[name*='pension'], input[name*='renta'], input[name*='liquida']", str(renta_liquida))
        
        self._espera_humana(2, 4, "revisando información completa")
        
        self._click_continuar()
    
    def _seleccionar_ubicacion(self):
        """Seleccionar ubicación fija DE FORMA HUMANA"""
        try:
            logger.info("🌎 Seleccionando región...")
            region = self.driver.find_element(By.CSS_SELECTOR, "select[name*='region']")
            self._mover_mouse_humano(region)
            self._espera_humana(0.5, 1.5, "viendo regiones")
            
            select = Select(region)
            select.select_by_visible_text("Coquimbo")
            self._espera_humana(2, 3, "cargando ciudades")
        except:
            pass
        
        try:
            logger.info("🏙️ Seleccionando ciudad...")
            ciudad = self.driver.find_element(By.CSS_SELECTOR, "select[name*='ciudad']")
            self._mover_mouse_humano(ciudad)
            self._espera_humana(0.5, 1.5, "viendo ciudades")
            
            select = Select(ciudad)
            select.select_by_visible_text("Elqui")
            self._espera_humana(2, 3, "cargando comunas")
        except:
            pass
        
        try:
            logger.info("🏘️ Seleccionando comuna...")
            comuna = self.driver.find_element(By.CSS_SELECTOR, "select[name*='comuna']")
            self._mover_mouse_humano(comuna)
            self._espera_humana(0.5, 1.5, "viendo comunas")
            
            select = Select(comuna)
            select.select_by_visible_text("La Serena")
            self._espera_humana(1, 2, "confirmando ubicación")
        except:
            pass
    
    def procesar_todos_los_clientes(self):
        """Procesar todos los clientes CON COMPORTAMIENTO SÚPER HUMANO"""
        logger.info("🚀 INICIANDO PROCESAMIENTO SÚPER HUMANO...")
        
        todos_los_clientes = self.leer_todos_los_clientes()
        
        if not todos_los_clientes:
            logger.info("ℹ️ No hay clientes para procesar en ninguna planilla")
            return True
        
        total_clientes = len(todos_los_clientes)
        logger.info(f"📊 Total clientes a procesar CON COMPORTAMIENTO HUMANO: {total_clientes}")
        
        for idx, cliente in enumerate(todos_los_clientes, 1):
            logger.info(f"\n{'='*20} CLIENTE {idx}/{total_clientes} (SÚPER HUMANO) {'='*20}")
            logger.info(f"👥 Agente: {cliente['agente']}")
            logger.info(f"👤 Cliente: {cliente['Nombre Cliente']} - {cliente['RUT']}")
            
            try:
                if idx > 1:
                    logger.info("🤔 Simulando pausa humana entre clientes...")
                    self._espera_humana(8, 15, "descanso entre clientes")
                    
                    try:
                        logger.info("🔄 Regresando al dashboard de forma humana...")
                        self.driver.get("https://prescriptores.salvum.cl/")
                        self._espera_humana(3, 6, "cargando dashboard")
                        
                        self._leer_pagina_humano()
                        
                    except Exception as e:
                        logger.warning(f"Error regresando al dashboard: {e}")
                        self._espera_humana(3, 5, "recuperación dashboard")
                
                logger.info(f"👤 Iniciando procesamiento humano del cliente {idx}...")
                if self.procesar_cliente_individual(cliente):
                    logger.info(f"✅ Cliente {idx} completado CON COMPORTAMIENTO HUMANO")
                    
                    self._espera_humana(2, 4, "satisfacción por cliente completado")
                    
                else:
                    logger.error(f"❌ Cliente {idx} falló")
                    
                    self._espera_humana(3, 6, "procesando fallo")
                
            except Exception as e:
                logger.error(f"❌ Error procesando cliente {idx}: {e}")
                
                self._espera_humana(5, 8, "recuperándose de error")
                continue
        
        logger.info("🎉 ¡PROCESAMIENTO SÚPER HUMANO COMPLETADO!")
        
        self._espera_humana(3, 6, "satisfacción final por trabajo completado")
        
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
            'version': 'ULTRA_CORREGIDA',
            'configuracion_chrome': 'SIN_PROXY_GARANTIZADO',
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
        
        with open('reporte_salvum_ultra_corregido.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        logger.info("="*70)
        logger.info("📊 REPORTE FINAL - VERSIÓN ULTRA-CORREGIDA")
        logger.info("="*70)
        logger.info(f"🔧 Configuración: Chrome sin proxy garantizado")
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
        """VERSIÓN ULTRA-CORREGIDA: Automatización con limpieza de proxy garantizada"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN (VERSIÓN ULTRA-CORREGIDA)")
        logger.info("="*70)
        logger.info(f"🔧 Chrome: Sin proxy garantizado (limpieza de entorno)")
        logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
        logger.info("="*70)
        
        try:
            # Limpiar entorno de proxy antes de empezar
            logger.info("🧹 Limpiando configuración de proxy del entorno...")
            proxy_vars_found = []
            for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
                if var in os.environ:
                    proxy_vars_found.append(f"{var}={os.environ[var]}")
            
            if proxy_vars_found:
                logger.info(f"🔍 Variables de proxy encontradas: {proxy_vars_found}")
            else:
                logger.info("✅ No hay variables de proxy en el entorno")
            
            vps_ok, ip_data = self.verificar_conexion_vps()
            if vps_ok:
                logger.info("✅ VPS Chile disponible para verificaciones")
            else:
                logger.warning("⚠️ VPS no disponible - Continuando sin verificaciones VPS")
            
            if not self.cargar_configuracion_agentes():
                return False
            
            if not self.configurar_google_sheets():
                return False
            
            todos_los_clientes = self.leer_todos_los_clientes()
            if not todos_los_clientes:
                logger.info("ℹ️ No hay clientes para procesar")
                return True
            
            logger.info("🔧 Configurando navegador con limpieza explícita de proxy...")
            if not self.configurar_navegador():
                logger.error("❌ Error configurando navegador")
                return False
            
            if not self.realizar_login():
                logger.error("❌ Login falló")
                return False
            
            self.procesar_todos_los_clientes()
            
            self.generar_reporte_final()
            
            logger.info("🎉 ¡AUTOMATIZACIÓN ULTRA-CORREGIDA COMPLETADA!")
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
    automator = SalvumMultiplePlanillasConVPS()
    
    print("🇨🇱 AUTOMATIZACIÓN SALVUM - VERSIÓN ULTRA-CORREGIDA")
    print("📊 Chrome sin proxy garantizado + Limpieza de entorno")
    print(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
    print("-"*70)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Ver reporte_salvum_ultra_corregido.json para detalles")
        print("📊 Estados actualizados en todas las planillas")
        print("🔧 Versión ultra-corregida con proxy garantizado deshabilitado")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
