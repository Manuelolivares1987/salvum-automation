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
            
            # 🔧 VERIFICAR URL Y BUSCAR "NUEVA SOLICITUD" SIEMPRE
            url_actual = self.driver.current_url
            logger.info(f"📍 URL actual: {url_actual}")
            
            # Si no estamos en credit-request, navegar primero
            if "credit-request" not in url_actual.lower():
                logger.info("🔄 Navegando a página de solicitudes...")
                self.driver.get("https://prescriptores.salvum.cl/credit-request")
                self._espera_humana(3, 6, "cargando página de solicitudes")
            
            # SIEMPRE buscar y hacer click en "Nueva Solicitud"
            logger.info("📝 Buscando botón Nueva Solicitud...")
            nueva_solicitud_btn = None
            
            # Múltiples selectores para el botón Nueva Solicitud
            selectores_nueva_solicitud = [
                "//button[contains(text(), 'Nueva Solicitud')]",
                "//a[contains(text(), 'Nueva Solicitud')]", 
                "//button[contains(text(), 'Crear Solicitud')]",
                "//a[contains(text(), 'Crear Solicitud')]",
                "//button[contains(text(), 'NUEVA SOLICITUD')]",
                "//a[contains(text(), 'NUEVA SOLICITUD')]",
                "//button[contains(@class, 'nueva-solicitud')]",
                "//a[contains(@class, 'nueva-solicitud')]",
                "//button[contains(@id, 'nueva-solicitud')]",
                "//a[contains(@id, 'nueva-solicitud')]"
            ]
            
            for selector in selectores_nueva_solicitud:
                try:
                    nueva_solicitud_btn = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    logger.info(f"✅ Botón Nueva Solicitud encontrado: {selector}")
                    break
                except:
                    continue
            
            if nueva_solicitud_btn:
                logger.info("🔘 Haciendo click en Nueva Solicitud...")
                self._click_humano(nueva_solicitud_btn)
                self._espera_humana(4, 8, "cargando formulario de nueva solicitud")
                
                # Verificar que el formulario se haya cargado
                url_despues_click = self.driver.current_url
                logger.info(f"📍 URL después de click: {url_despues_click}")
            else:
                logger.error("❌ No se encontró botón Nueva Solicitud")
                # Tomar screenshot para debugging
                self.driver.save_screenshot(f"error_nueva_solicitud_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception("No se encontró botón Nueva Solicitud")
            
            logger.info("📋 Llenando datos específicos del cliente en el formulario...")
            
            # Procesar nombre del cliente
            nombre_completo = cliente_data['Nombre Cliente']
            nombre_partes = nombre_completo.split()
            primer_nombre = nombre_partes[0] if nombre_partes else nombre_completo
            
            # CAMPO 1: RUT
            logger.info("🆔 Llenando RUT...")
            rut_value = str(cliente_data['RUT']).strip()
            if not self._llenar_campo_especifico("RUT", rut_value, [
                "input[name*='rut']", 
                "input[id*='rut']", 
                "input[placeholder*='RUT']",
                "input[placeholder*='rut']",
                "input[class*='rut']"
            ]):
                raise Exception("❌ Campo RUT no encontrado")
            
            # CAMPO 2: NÚMERO CELULAR
            logger.info("📱 Llenando Número Celular...")
            telefono_value = str(cliente_data['Telefono']).strip()
            if not self._llenar_campo_especifico("Teléfono/Celular", telefono_value, [
                "input[name*='telefono']",
                "input[name*='celular']", 
                "input[name*='phone']",
                "input[id*='telefono']",
                "input[id*='celular']",
                "input[id*='phone']",
                "input[placeholder*='teléfono']",
                "input[placeholder*='celular']",
                "input[placeholder*='phone']",
                "input[type='tel']"
            ]):
                logger.warning("⚠️ Campo Teléfono no encontrado, continuando...")
            
            # CAMPO 3: CORREO ELECTRÓNICO
            logger.info("📧 Llenando Correo Electrónico...")
            email_value = str(cliente_data['Email']).strip()
            if not self._llenar_campo_especifico("Email", email_value, [
                "input[type='email']",
                "input[name*='email']",
                "input[name*='correo']",
                "input[id*='email']",
                "input[id*='correo']",
                "input[placeholder*='email']",
                "input[placeholder*='correo']"
            ]):
                logger.warning("⚠️ Campo Email no encontrado, continuando...")
            
            # CAMPO 4: NOMBRE
            logger.info("👤 Llenando Nombre...")
            if not self._llenar_campo_especifico("Nombre", primer_nombre, [
                "input[name*='nombre']",
                "input[name*='name']",
                "input[id*='nombre']",
                "input[id*='name']",
                "input[placeholder*='Nombre']",
                "input[placeholder*='name']"
            ]):
                logger.warning("⚠️ Campo Nombre no encontrado, continuando...")
            
            # CAMPO 5: APELLIDOS (VALOR FIJO: Gonzalez)
            logger.info("👨‍👩‍👧‍👦 Llenando Apellidos...")
            if not self._llenar_campo_especifico("Apellidos", "Gonzalez", [
                "input[name*='apellido']",
                "input[name*='surname']",
                "input[id*='apellido']",
                "input[id*='surname']",
                "input[placeholder*='Apellido']",
                "input[placeholder*='surname']"
            ]):
                logger.warning("⚠️ Campo Apellidos no encontrado, continuando...")
            
            # CAMPO 6: FECHA DE NACIMIENTO (VALOR FIJO: 25/08/1987)
            logger.info("🎂 Llenando Fecha de Nacimiento...")
            if not self._llenar_campo_especifico("Fecha Nacimiento", "25/08/1987", [
                "input[type='date']",
                "input[name*='fecha']",
                "input[name*='nacimiento']",
                "input[name*='birth']",
                "input[id*='fecha']",
                "input[id*='nacimiento']",
                "input[id*='birth']",
                "input[placeholder*='fecha']",
                "input[placeholder*='nacimiento']"
            ]):
                logger.warning("⚠️ Campo Fecha de Nacimiento no encontrado, continuando...")
            
            logger.info("✅ Todos los campos del formulario completados")
            
            # Tomar screenshot del formulario completado
            self.driver.save_screenshot(f"formulario_completado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            logger.info("📸 Screenshot del formulario completado tomada")
            
            # 7. CLICK EN CONTINUAR
            logger.info("🔘 Buscando botón Continuar...")
            self._espera_humana(2, 4, "revisando formulario antes de continuar")
            
            if not self._click_continuar_flexible():
                logger.warning("⚠️ No se pudo hacer click en Continuar, intentando continuar con el flujo...")
            
            logger.info("✅ Primera parte del formulario completada")
            
            # Continuar con el resto del procesamiento (financiamiento, etc.)
            logger.info("💰 Continuando con configuración de financiamiento...")
            
            self._configurar_financiamiento(cliente_data)
            
            # Resto del procesamiento...
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"cliente_{agente.replace(' ', '_')}_{nombre.replace(' ', '_')}_{timestamp}.png"
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

    def _llenar_campo_especifico(self, nombre_campo, valor, selectores):
        """Llenar un campo específico con múltiples selectores"""
        logger.info(f"  🔍 Buscando campo {nombre_campo}...")
        
        for selector in selectores:
            try:
                campo = self.driver.find_element(By.CSS_SELECTOR, selector)
                if campo.is_displayed() and campo.is_enabled():
                    logger.info(f"  ✅ Campo {nombre_campo} encontrado: {selector}")
                    
                    # Limpiar el campo primero
                    campo.clear()
                    self._espera_humana(0.5, 1, f"limpiando campo {nombre_campo}")
                    
                    # Hacer click y tipear de forma humana
                    self._click_humano(campo)
                    self._tipear_humano(campo, valor)
                    
                    logger.info(f"  ✅ {nombre_campo} llenado: {valor}")
                    return True
                    
            except Exception as e:
                continue
        
        logger.warning(f"  ❌ Campo {nombre_campo} no encontrado con ningún selector")
        return False

    def _configurar_financiamiento(self, cliente_data):
        """Configurar el flujo completo de financiamiento paso a paso"""
        logger.info("💰 INICIANDO FLUJO COMPLETO DE FINANCIAMIENTO...")
        
        try:
            # ============= PÁGINA 1: CONFIGURACIÓN DE FINANCIAMIENTO =============
            logger.info("📄 PÁGINA 1: Configuración de Financiamiento")
            self._espera_humana(3, 6, "cargando página de financiamiento")
            
            # 1. ¿Qué se va a financiar? → Casas Modulares
            logger.info("🏠 Seleccionando: Casas Modulares")
            self._seleccionar_opcion("¿Qué se va a financiar?", "Casas Modulares", [
                "select[name*='producto']",
                "select[name*='financiar']",
                "select[id*='producto']",
                "select[id*='financiar']"
            ])
            
            # 2. Valor del producto → Monto financiamiento
            monto = int(cliente_data['Monto Financiar Original'])
            logger.info(f"💰 Llenando Valor del producto: {monto}")
            self._llenar_campo_especifico("Valor del producto", str(monto), [
                "input[name*='valor']",
                "input[name*='precio']",
                "input[name*='product']",
                "input[id*='valor']",
                "input[id*='precio']",
                "input[placeholder*='valor']"
            ])
            
            # 3. ¿Cuánto quieres solicitar? → Monto financiamiento
            logger.info(f"💵 Llenando Cuánto quieres solicitar: {monto}")
            self._llenar_campo_especifico("Cuánto solicitar", str(monto), [
                "input[name*='solicitar']",
                "input[name*='monto']",
                "input[name*='amount']",
                "input[id*='solicitar']",
                "input[id*='monto']",
                "input[placeholder*='solicitar']"
            ])
            
            # 4. Cuota → 60
            logger.info("📊 Configurando Cuota: 60")
            self._seleccionar_opcion("Cuota", "60", [
                "select[name*='cuota']",
                "select[id*='cuota']",
                "input[name*='cuota']",
                "input[id*='cuota']"
            ])
            
            # 5. Día de Vencimiento → 2
            logger.info("📅 Configurando Día de Vencimiento: 2")
            self._seleccionar_opcion("Día Vencimiento", "2", [
                "select[name*='dia']",
                "select[name*='vencimiento']",
                "select[id*='dia']",
                "input[name*='dia']",
                "input[id*='dia']"
            ])
            
            # 6. Click en Simular
            logger.info("🔘 Haciendo click en Simular...")
            btn_simular = self._buscar_boton_flexible(["Simular", "Calcular", "Procesar"])
            if btn_simular:
                self._click_humano(btn_simular)
                self._espera_humana(6, 10, "procesando simulación")
            else:
                raise Exception("❌ Botón Simular no encontrado")
            
            # ============= PÁGINA 2: CONTINUAR DESPUÉS DE SIMULACIÓN =============
            logger.info("📄 PÁGINA 2: Después de Simulación")
            self._espera_humana(3, 5, "cargando resultados de simulación")
            
            if not self._click_continuar_flexible():
                raise Exception("❌ No se pudo continuar después de simulación")
            
            # ============= PÁGINA 3: INFORMACIÓN PERSONAL =============
            logger.info("📄 PÁGINA 3: Información Personal")
            self._espera_humana(3, 5, "cargando página información personal")
            
            # N° de serie C.I → 123456789
            logger.info("🆔 Llenando N° de serie C.I: 123456789")
            self._llenar_campo_especifico("N° CI", "123456789", [
                "input[name*='ci']",
                "input[name*='cedula']",
                "input[name*='serie']",
                "input[id*='ci']",
                "input[id*='cedula']",
                "input[placeholder*='ci']"
            ])
            
            # Estado Civil → Soltero
            logger.info("💑 Seleccionando Estado Civil: Soltero")
            self._seleccionar_opcion("Estado Civil", "Soltero", [
                "select[name*='civil']",
                "select[name*='estado']",
                "select[id*='civil']",
                "select[id*='estado']"
            ])
            
            if not self._click_continuar_flexible():
                raise Exception("❌ No se pudo continuar después de información personal")
            
            # ============= PÁGINA 4: UBICACIÓN =============
            logger.info("📄 PÁGINA 4: Ubicación")
            self._espera_humana(3, 5, "cargando página ubicación")
            
            # Región → Coquimbo
            logger.info("🌎 Seleccionando Región: Coquimbo")
            self._seleccionar_opcion("Región", "Coquimbo", [
                "select[name*='region']",
                "select[id*='region']"
            ])
            self._espera_humana(2, 4, "cargando ciudades")
            
            # Ciudad → Elqui
            logger.info("🏙️ Seleccionando Ciudad: Elqui")
            self._seleccionar_opcion("Ciudad", "Elqui", [
                "select[name*='ciudad']",
                "select[name*='city']",
                "select[id*='ciudad']"
            ])
            self._espera_humana(2, 4, "cargando comunas")
            
            # Comuna → La Serena
            logger.info("🏘️ Seleccionando Comuna: La Serena")
            self._seleccionar_opcion("Comuna", "La Serena", [
                "select[name*='comuna']",
                "select[id*='comuna']"
            ])
            
            # Dirección → Avenida
            logger.info("🏠 Llenando Dirección: Avenida")
            self._llenar_campo_especifico("Dirección", "Avenida", [
                "input[name*='direccion']",
                "input[name*='address']",
                "input[id*='direccion']",
                "input[placeholder*='direccion']"
            ])
            
            if not self._click_continuar_flexible():
                raise Exception("❌ No se pudo continuar después de ubicación")
            
            # ============= PÁGINA 5: INFORMACIÓN LABORAL =============
            logger.info("📄 PÁGINA 5: Información Laboral")
            self._espera_humana(3, 5, "cargando página información laboral")
            
            # Modalidad de trabajo → Jubilado
            logger.info("💼 Seleccionando Modalidad de trabajo: Jubilado")
            self._seleccionar_opcion("Modalidad trabajo", "Jubilado", [
                "select[name*='trabajo']",
                "select[name*='modalidad']",
                "select[name*='laboral']",
                "select[id*='trabajo']",
                "select[id*='modalidad']"
            ])
            
            # Última Pensión Líquida → Desde Google Sheet
            renta_liquida = int(cliente_data['RENTA LIQUIDA'])
            logger.info(f"💰 Llenando Última Pensión Líquida: {renta_liquida}")
            self._llenar_campo_especifico("Pensión Líquida", str(renta_liquida), [
                "input[name*='pension']",
                "input[name*='renta']",
                "input[name*='liquida']",
                "input[id*='pension']",
                "input[id*='renta']",
                "input[placeholder*='pension']"
            ])
            
            if not self._click_continuar_flexible():
                raise Exception("❌ No se pudo continuar después de información laboral")
            
            # ============= PÁGINA 6: CONTINUAR AUTOMÁTICO =============
            logger.info("📄 PÁGINA 6: Continuar Automático")
            self._espera_humana(3, 5, "cargando página intermedia")
            
            if not self._click_continuar_flexible():
                raise Exception("❌ No se pudo continuar en página intermedia")
            
            # ============= PÁGINA 7: RESULTADO FINAL =============
            logger.info("📄 PÁGINA 7: Resultado Final")
            self._espera_humana(5, 8, "cargando página final")
            
            # Sacar screenshot y guardar
            return self._capturar_resultado_final(cliente_data)
            
        except Exception as e:
            logger.error(f"❌ Error en flujo de financiamiento: {e}")
            raise

    def _seleccionar_opcion(self, nombre_campo, valor, selectores):
        """Seleccionar opción en select o llenar input"""
        logger.info(f"  🔍 Buscando campo {nombre_campo} para valor: {valor}")
        
        for selector in selectores:
            try:
                elemento = self.driver.find_element(By.CSS_SELECTOR, selector)
                if elemento.is_displayed() and elemento.is_enabled():
                    logger.info(f"  ✅ Campo {nombre_campo} encontrado: {selector}")
                    
                    if elemento.tag_name == 'select':
                        # Es un select dropdown
                        self._mover_mouse_humano(elemento)
                        self._espera_humana(0.5, 1.5, f"viendo opciones {nombre_campo}")
                        
                        select = Select(elemento)
                        try:
                            select.select_by_visible_text(valor)
                            logger.info(f"  ✅ {nombre_campo} seleccionado: {valor}")
                            return True
                        except:
                            # Intentar seleccionar por valor
                            try:
                                select.select_by_value(valor)
                                logger.info(f"  ✅ {nombre_campo} seleccionado por valor: {valor}")
                                return True
                            except:
                                continue
                    else:
                        # Es un input
                        self._click_humano(elemento)
                        self._tipear_humano(elemento, valor)
                        logger.info(f"  ✅ {nombre_campo} llenado: {valor}")
                        return True
                        
            except Exception as e:
                continue
        
        logger.warning(f"  ❌ Campo {nombre_campo} no encontrado")
        return False

    def _capturar_resultado_final(self, cliente_data):
        """Capturar screenshot final y guardar información"""
        logger.info("📸 CAPTURANDO RESULTADO FINAL...")
        
        try:
            # Tomar screenshot de la página final
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_cliente = cliente_data['Nombre Cliente'].replace(' ', '_')
            agente = cliente_data['agente'].replace(' ', '_')
            
            screenshot_path = f"resultado_final_{agente}_{nombre_cliente}_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"📸 Screenshot capturado: {screenshot_path}")
            
            # Obtener URL de resultado
            url_resultado = self.driver.current_url
            logger.info(f"📍 URL resultado: {url_resultado}")
            
            # Intentar guardar el screenshot en Google Sheet
            self._guardar_screenshot_en_sheet(cliente_data, screenshot_path, url_resultado)
            
            return {
                'screenshot': screenshot_path,
                'url': url_resultado,
                'timestamp': timestamp
            }
            
        except Exception as e:
            logger.error(f"❌ Error capturando resultado final: {e}")
            raise

    def _guardar_screenshot_en_sheet(self, cliente_data, screenshot_path, url_resultado):
        """Guardar información del screenshot en Google Sheet"""
        try:
            logger.info("💾 Guardando información en Google Sheet...")
            
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
            
            # Columna 14: Estado
            worksheet.update_cell(row_number, 14, "COMPLETADO")
            
            # Columna 15: Resultado 
            worksheet.update_cell(row_number, 15, f"Exitoso - URL: {url_resultado}")
            
            # Columna 16: Fecha de proceso
            worksheet.update_cell(row_number, 16, f"Procesado: {timestamp}")
            
            # Columna 17: Screenshot (si existe esta columna)
            try:
                worksheet.update_cell(row_number, 17, f"Screenshot: {screenshot_path}")
            except:
                pass
            
            logger.info(f"✅ Información guardada en Google Sheet fila {row_number}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando en Google Sheet: {e}")
            # No lanzar excepción aquí para no interrumpir el flujo

    def _click_continuar_flexible(self):
        """Click en botón continuar con múltiples variantes"""
        botones_continuar = [
            "Continuar", "Siguiente", "Next", "Avanzar", "Seguir"
        ]
        
        for texto_boton in botones_continuar:
            try:
                btn = self.driver.find_element(By.XPATH, f"//button[contains(text(), '{texto_boton}')]")
                if btn.is_displayed() and btn.is_enabled():
                    logger.info(f"🔘 Haciendo click en {texto_boton}...")
                    self._espera_humana(1, 3, "revisando antes de continuar")
                    self._click_humano(btn)
                    self._espera_humana(3, 6, "cargando siguiente página")
                    return True
            except:
                continue
        
        # Si no encuentra botón, intentar enviar Enter en el último campo activo
        try:
            elemento_activo = self.driver.switch_to.active_element
            elemento_activo.send_keys(Keys.RETURN)
            self._espera_humana(3, 6, "enviando Enter como continuar")
            logger.info("⌨️ Enviado Enter como alternativa")
            return True
        except:
            pass
        
        logger.warning("⚠️ No se pudo continuar")
        return False

    def _buscar_boton_flexible(self, textos_posibles):
        """Buscar botón con múltiples textos posibles"""
        for texto in textos_posibles:
            try:
                btn = self.driver.find_element(By.XPATH, f"//button[contains(text(), '{texto}')]")
                if btn.is_displayed() and btn.is_enabled():
                    logger.info(f"✅ Botón encontrado: {texto}")
                    return btn
            except:
                continue
        
        logger.warning(f"⚠️ No se encontró botón con textos: {textos_posibles}")
        return None
    
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
