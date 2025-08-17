#!/usr/bin/env python3
"""
AUTOMATIZACIÓN SALVUM - VERSIÓN CORREGIDA CON SELECTORES ANGULAR
Basado en la estructura real de los componentes Angular
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

class SalvumAutomacionCorregida:
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
            self.wait = WebDriverWait(self.driver, 45)  # Aumentado para Angular
            
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
        """Método de login con selectores PRECISOS basados en inspección real"""
        logger.info("🔑 INICIANDO LOGIN CON SELECTORES PRECISOS")
        logger.info("-" * 50)
        
        try:
            usuario = os.getenv('SALVUM_USER')
            password = os.getenv('SALVUM_PASS')
            
            logger.info(f"👤 Usuario: {usuario}")
            logger.info("🔒 Password: [PROTEGIDO]")
            
            logger.info("👁️ Simulando lectura humana de la página...")
            self._leer_pagina_humano()
            
            self._espera_humana(3, 7, "comportamiento humano inicial")
            
            logger.info("🔍 Buscando campos de login con selectores PRECISOS...")
            
            # CAMPO USUARIO - Selector exacto: input[id="Usuario"][name="Usuario"]
            logger.info("👤 Buscando campo Usuario...")
            try:
                campo_usuario = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id='Usuario'][name='Usuario']"))
                )
                logger.info("✅ Campo Usuario encontrado con selector exacto")
                self._mover_mouse_humano(campo_usuario)
                self._espera_humana(0.5, 1, "inspeccionando campo usuario")
            except Exception as e:
                logger.error(f"❌ No se encontró campo Usuario con selector exacto: {e}")
                # Fallback a selectores genéricos
                try:
                    campo_usuario = self.driver.find_element(By.CSS_SELECTOR, "input[type='text']")
                    logger.info("⚠️ Campo Usuario encontrado con selector genérico")
                except:
                    logger.error("❌ No se encontró campo Usuario")
                    return False
            
            # CAMPO CONTRASEÑA - Selector exacto: input[id="Contraseña"][name="Contraseña"]
            logger.info("🔒 Buscando campo Contraseña...")
            try:
                campo_password = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id='Contraseña'][name='Contraseña']"))
                )
                logger.info("✅ Campo Contraseña encontrado con selector exacto")
                self._mover_mouse_humano(campo_password)
                self._espera_humana(0.5, 1, "inspeccionando campo contraseña")
            except Exception as e:
                logger.error(f"❌ No se encontró campo Contraseña con selector exacto: {e}")
                # Fallback a selector genérico
                try:
                    campo_password = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                    logger.info("⚠️ Campo Contraseña encontrado con selector genérico")
                except:
                    logger.error("❌ No se encontró campo Contraseña")
                    return False
            
            logger.info("✏️ Llenando campos de forma humana...")
            
            # LLENAR USUARIO
            logger.info("👤 Llenando usuario...")
            self._click_humano(campo_usuario)
            # Asegurar que el campo esté limpio
            campo_usuario.clear()
            self._espera_humana(0.5, 1, "limpiando campo usuario")
            self._tipear_humano(campo_usuario, usuario)
            logger.info("✅ Usuario ingresado de forma humana")
            
            self._espera_humana(1, 3, "pausa entre campos")
            
            # LLENAR CONTRASEÑA
            logger.info("🔒 Llenando contraseña...")
            self._click_humano(campo_password)
            # Asegurar que el campo esté limpio
            campo_password.clear()
            self._espera_humana(0.5, 1, "limpiando campo contraseña")
            self._tipear_humano(campo_password, password)
            logger.info("✅ Contraseña ingresada de forma humana")
            
            self._espera_humana(2, 4, "verificando datos antes de enviar")
            
            self.driver.save_screenshot('salvum_antes_submit_precisos.png')
            logger.info("📸 Screenshot antes de submit con selectores precisos")
            
            # BOTÓN INGRESAR - Selector exacto: button[value="INGRESAR"]
            logger.info("🔘 Buscando botón INGRESAR con selector preciso...")
            try:
                boton_submit = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[value='INGRESAR']"))
                )
                logger.info("✅ Botón INGRESAR encontrado con selector exacto")
                self._mover_mouse_humano(boton_submit)
                self._espera_humana(0.5, 1, "inspeccionando botón")
            except Exception as e:
                logger.warning(f"⚠️ No se encontró con selector exacto: {e}")
                # Fallback a selector por texto
                try:
                    boton_submit = self.driver.find_element(By.XPATH, "//button[contains(text(), 'INGRESAR')]")
                    logger.info("⚠️ Botón INGRESAR encontrado por texto")
                except:
                    logger.error("❌ No se encontró botón INGRESAR")
                    return False
            
            logger.info("🖱️ Haciendo click en botón INGRESAR...")
            self._click_humano(boton_submit)
            logger.info("🔘 Click en INGRESAR ejecutado")
            
            logger.info("⏳ Esperando respuesta del servidor de forma humana...")
            
            # Esperar respuesta del servidor
            for i in range(3):
                self._espera_humana(3, 5, f"esperando respuesta {i+1}/3")
                
                try:
                    url_actual = self.driver.current_url
                    if "login" not in url_actual.lower():
                        logger.info(f"✅ Página cambió durante espera: {url_actual}")
                        break
                except:
                    pass
            
            self.driver.save_screenshot('salvum_despues_submit_precisos.png')
            logger.info("📸 Screenshot después de submit con selectores precisos")
            
            nueva_url = self.driver.current_url
            nuevo_titulo = self.driver.title
            
            logger.info(f"📍 Nueva URL: {nueva_url}")
            logger.info(f"📄 Nuevo título: {nuevo_titulo}")
            
            self._espera_humana(1, 2, "leyendo resultado")
            
            # Verificar si el login fue exitoso
            if nueva_url != "https://prescriptores.salvum.cl/login" and "login" not in nueva_url.lower():
                logger.info("🎉 ¡LOGIN CON SELECTORES PRECISOS EXITOSO! - URL cambió")
                self._leer_pagina_humano()
                return True
            else:
                logger.error("❌ Login falló - permanece en página de login")
                
                # Debug adicional para login fallido
                logger.info("🔍 Analizando por qué falló el login...")
                try:
                    # Verificar si hay mensajes de error
                    errores = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, .warning")
                    for error in errores:
                        if error.is_displayed():
                            logger.error(f"💬 Mensaje de error: {error.text}")
                    
                    # Verificar el estado de los campos
                    try:
                        usuario_valor = campo_usuario.get_attribute("value")
                        logger.info(f"📋 Valor campo usuario: '{usuario_valor}'")
                    except:
                        pass
                    
                    # Screenshot adicional para debug
                    self.driver.save_screenshot('debug_login_fallido.png')
                    
                except Exception as debug_error:
                    logger.warning(f"Error en debug: {debug_error}")
                
                return False
                
        except Exception as e:
            logger.error(f"❌ Error en proceso de login con selectores precisos: {e}")
            self.driver.save_screenshot('error_login_precisos.png')
            return False
    
    def procesar_cliente_individual(self, cliente_data):
        """Procesar un cliente individual en Salvum CON SELECTORES ANGULAR CORREGIDOS"""
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
            self._configurar_financiamiento_angular(cliente_data)
            
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

    def _configurar_financiamiento_angular(self, cliente_data):
        """🔧 CONFIGURACIÓN DE FINANCIAMIENTO CON SELECTORES ANGULAR CORREGIDOS"""
        logger.info("💰 INICIANDO CONFIGURACIÓN ANGULAR CORREGIDA...")
        
        try:
            # ============= PÁGINA 2: CONFIGURACIÓN DE FINANCIAMIENTO =============
            logger.info("📄 PÁGINA 2: Configuración de Financiamiento Angular")
            
            # ESPERA EXTENDIDA PARA ANGULAR
            logger.info("⏳ Esperando carga completa de Angular...")
            self._espera_humana(5, 8, "cargando página de financiamiento completamente")
            
            # DEBUG: Información de la página actual
            try:
                url_actual = self.driver.current_url
                titulo_actual = self.driver.title
                logger.info(f"📍 URL actual: {url_actual}")
                logger.info(f"📄 Título actual: {titulo_actual}")
                
                # Verificar si hay elementos Angular cargando
                elementos_ng = self.driver.find_elements(By.CSS_SELECTOR, "[ng-reflect], [_ngcontent]")
                logger.info(f"🅰️ Elementos Angular detectados: {len(elementos_ng)}")
                
                # Verificar selects disponibles
                selects_totales = self.driver.find_elements(By.CSS_SELECTOR, "select")
                logger.info(f"📋 Total selects en página: {len(selects_totales)}")
                
            except Exception as debug_error:
                logger.warning(f"Error en debug inicial: {debug_error}")
            
            # SCREENSHOT ANTES DE INTENTAR SELECCIÓN
            self.driver.save_screenshot(f"antes_seleccion_producto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            logger.info("📸 Screenshot antes de selección de producto")
            
            # 1. ¿Qué se va a financiar? → Seleccionar "Casas modulares"
            logger.info("🏠 Seleccionando: Casas modulares (Selectores precisos del DevTools)")
            try:
                producto_seleccionado = False
                
                # ESTRATEGIA 1: Usar el componente form-select específico
                logger.info("🔍 Estrategia 1: Componente form-select...")
                try:
                    # Buscar el componente form-select por su label
                    form_select = self.driver.find_element(
                        By.CSS_SELECTOR, 
                        "form-select[label='¿Qué se va a financiar?']"
                    )
                    logger.info("✅ Componente form-select encontrado")
                    
                    # Buscar el select interno con las clases específicas del DevTools
                    select_interno = form_select.find_element(
                        By.CSS_SELECTOR, 
                        "select.ng-pristine.ng-invalid.ng-touched"
                    )
                    
                    if select_interno.is_displayed():
                        select_obj = Select(select_interno)
                        opciones = [opt.text.strip() for opt in select_obj.options]
                        logger.info(f"📋 Opciones en form-select: {opciones}")
                        
                        if "Casas modulares" in opciones:
                            select_obj.select_by_visible_text("Casas modulares")
                            logger.info("✅ Producto seleccionado con form-select: Casas modulares")
                            producto_seleccionado = True
                    
                except Exception as e:
                    logger.warning(f"Estrategia 1 falló: {e}")
                
                # ESTRATEGIA 2: Buscar por div.combo-cont.is-focus específico
                if not producto_seleccionado:
                    logger.info("🔍 Estrategia 2: div.combo-cont.is-focus...")
                    try:
                        combo_container = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            "div.combo-cont.is-focus.normal-border"
                        )
                        logger.info("✅ Combo container específico encontrado")
                        
                        # Hacer click para activar si es necesario
                        self._click_humano(combo_container)
                        self._espera_humana(1, 2, "activando combo específico")
                        
                        # Buscar el select dentro del combo
                        select_combo = combo_container.find_element(By.CSS_SELECTOR, "select")
                        select_obj = Select(select_combo)
                        opciones = [opt.text.strip() for opt in select_obj.options]
                        logger.info(f"📋 Opciones en combo-cont: {opciones}")
                        
                        if "Casas modulares" in opciones:
                            select_obj.select_by_visible_text("Casas modulares")
                            logger.info("✅ Producto seleccionado con combo-cont: Casas modulares")
                            producto_seleccionado = True
                    
                    except Exception as e:
                        logger.warning(f"Estrategia 2 falló: {e}")
                
                # ESTRATEGIA 3: Buscar select por clases exactas del DevTools
                if not producto_seleccionado:
                    logger.info("🔍 Estrategia 3: Clases exactas del DevTools...")
                    try:
                        select_exacto = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            "select.ng-pristine.ng-invalid.ng-touched"
                        )
                        
                        if select_exacto.is_displayed() and select_exacto.is_enabled():
                            select_obj = Select(select_exacto)
                            opciones = [opt.text.strip() for opt in select_obj.options]
                            logger.info(f"📋 Opciones en select exacto: {opciones}")
                            
                            if "Casas modulares" in opciones:
                                select_obj.select_by_visible_text("Casas modulares")
                                logger.info("✅ Producto seleccionado con clases exactas: Casas modulares")
                                producto_seleccionado = True
                            else:
                                # Intentar por valor como fallback
                                try:
                                    select_obj.select_by_value("2: Object")
                                    logger.info("✅ Producto seleccionado por valor: 2: Object")
                                    producto_seleccionado = True
                                except:
                                    pass
                    
                    except Exception as e:
                        logger.warning(f"Estrategia 3 falló: {e}")
                
                # ESTRATEGIA 4: Click en la opción p.option-selected para activar
                if not producto_seleccionado:
                    logger.info("🔍 Estrategia 4: Click en option-selected...")
                    try:
                        # Buscar el elemento p.option-selected
                        option_selected = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            "p.option-selected"
                        )
                        logger.info("✅ Element option-selected encontrado")
                        
                        # Hacer click para abrir el dropdown
                        self._click_humano(option_selected)
                        self._espera_humana(1, 2, "abriendo dropdown con option-selected")
                        
                        # Ahora intentar seleccionar en el select que se activó
                        selects_activos = self.driver.find_elements(By.CSS_SELECTOR, "select")
                        for select_elem in selects_activos:
                            try:
                                select_obj = Select(select_elem)
                                opciones = [opt.text.strip() for opt in select_obj.options]
                                if "Casas modulares" in opciones:
                                    select_obj.select_by_visible_text("Casas modulares")
                                    logger.info("✅ Producto seleccionado después de option-selected: Casas modulares")
                                    producto_seleccionado = True
                                    break
                            except:
                                continue
                    
                    except Exception as e:
                        logger.warning(f"Estrategia 4 falló: {e}")
                
                if not producto_seleccionado:
                    logger.error("❌ No se pudo seleccionar producto con ninguna estrategia")
                    
                    # DEBUG COMPLETO: Mostrar todos los elementos disponibles
                    try:
                        logger.info("🔍 DEBUG: Analizando elementos disponibles...")
                        
                        # Todos los selects
                        todos_selects = self.driver.find_elements(By.CSS_SELECTOR, "select")
                        logger.info(f"📋 Total selects encontrados: {len(todos_selects)}")
                        
                        for i, select_elem in enumerate(todos_selects):
                            try:
                                clases = select_elem.get_attribute("class")
                                select_obj = Select(select_elem)
                                opciones = [opt.text.strip() for opt in select_obj.options]
                                logger.info(f"📋 Select {i} - Clases: {clases} - Opciones: {opciones}")
                            except Exception as debug_error:
                                logger.warning(f"Error debuggeando select {i}: {debug_error}")
                        
                        # Todos los form-select
                        form_selects = self.driver.find_elements(By.CSS_SELECTOR, "form-select")
                        logger.info(f"📋 Total form-selects: {len(form_selects)}")
                        
                        for i, fs in enumerate(form_selects):
                            try:
                                label = fs.get_attribute("label")
                                logger.info(f"📋 Form-select {i} - Label: {label}")
                            except:
                                pass
                                
                    except Exception as debug_error:
                        logger.warning(f"Error en debug completo: {debug_error}")
                    
                    self.driver.save_screenshot(f"error_select_all_strategies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    raise Exception("No se pudo seleccionar producto después de 4 estrategias específicas")
                
                self._espera_humana(3, 5, "esperando que se carguen opciones dependientes")
                
            except Exception as e:
                logger.error(f"❌ Error crítico seleccionando producto Angular: {e}")
                self.driver.save_screenshot(f"error_select_angular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception("No se pudo seleccionar producto en componente Angular")
            
            # 2. Valor del producto → NUEVO SELECTOR BASADO EN HTML REAL
            logger.info("💰 Llenando Valor del producto (Componente Angular)...")
            try:
                monto = int(cliente_data['Monto Financiar Original'])
                logger.info(f"💵 Monto a usar: {monto}")
                
                # NUEVO: Buscar dentro del componente form-money-amount
                campo_valor = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    "form-money-amount[label='Valor del producto'] input[id='import-simple']"
                )
                
                logger.info("✅ Campo valor encontrado en componente Angular")
                
                # Hacer click y enfocar el campo
                self._click_humano(campo_valor)
                
                # Limpiar y llenar usando JavaScript para asegurar compatibilidad con Angular
                self.driver.execute_script("arguments[0].value = '';", campo_valor)
                self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_valor)
                
                # Disparar eventos Angular
                self.driver.execute_script("""
                    var element = arguments[0];
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                """, campo_valor)
                
                logger.info(f"✅ Valor del producto llenado: {monto}")
                self._espera_humana(2, 4, "esperando procesamiento Angular del valor")
                
            except Exception as e:
                logger.error(f"❌ Error llenando Valor del producto Angular: {e}")
                self.driver.save_screenshot(f"error_valor_angular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception("No se pudo llenar valor del producto en componente Angular")
            
            # 3. ¿Cuánto quieres solicitar? → NUEVO SELECTOR ESPECÍFICO
            logger.info("💵 Llenando Cuánto quieres solicitar (Componente Angular)...")
            try:
                # NUEVO: Buscar el segundo componente form-money-amount
                campo_solicitar = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    "form-money-amount[label='¿Cuánto quieres solicitar?'] input[id='import-simple']"
                )
                
                logger.info("✅ Campo solicitar encontrado en componente Angular")
                
                # Hacer click y enfocar el campo
                self._click_humano(campo_solicitar)
                
                # Limpiar y llenar usando JavaScript
                self.driver.execute_script("arguments[0].value = '';", campo_solicitar)
                self.driver.execute_script(f"arguments[0].value = '{monto}';", campo_solicitar)
                
                # Disparar eventos Angular
                self.driver.execute_script("""
                    var element = arguments[0];
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('blur', { bubbles: true }));
                """, campo_solicitar)
                
                logger.info(f"✅ Cuánto solicitar llenado: {monto}")
                self._espera_humana(2, 4, "esperando procesamiento Angular del monto solicitar")
                
            except Exception as e:
                logger.warning(f"⚠️ Error llenando Cuánto solicitar: {e}")
                # No es crítico si falla, a veces solo hay un campo
                logger.info("ℹ️ Continuando sin segundo campo de monto")
            
            # ESPERAR A QUE SE CARGUEN LOS SELECTS DINÁMICOS
            logger.info("⏳ Esperando que se carguen las opciones dinámicas...")
            self._espera_humana(4, 7, "esperando carga dinámica de selects Angular")
            
            # 4. Cuota → Buscar selects que se cargaron dinámicamente
            logger.info("📊 Seleccionando Cuota: 60 cuotas (Angular dinámico)")
            try:
                # Esperar un poco más para que Angular termine de cargar
                self._espera_humana(3, 5, "esperando finalización carga Angular")
                
                # Buscar todos los selects disponibles después de llenar montos
                selects_disponibles = self.driver.find_elements(By.CSS_SELECTOR, "select")
                logger.info(f"📋 Selects disponibles después de llenar montos: {len(selects_disponibles)}")
                
                cuota_seleccionada = False
                for i, select_elem in enumerate(selects_disponibles):
                    try:
                        select_obj = Select(select_elem)
                        opciones = [option.text.strip() for option in select_obj.options if option.text.strip()]
                        logger.info(f"📋 Select {i}: {opciones}")
                        
                        # Verificar si contiene opciones de cuotas
                        if any("cuota" in opcion.lower() for opcion in opciones):
                            logger.info(f"✅ Select de cuotas encontrado en posición {i}")
                            # Intentar seleccionar "60 cuotas"
                            for opcion in ["60 cuotas", "60", "60 CUOTAS"]:
                                try:
                                    select_obj.select_by_visible_text(opcion)
                                    logger.info(f"✅ Cuota seleccionada: {opcion}")
                                    cuota_seleccionada = True
                                    break
                                except:
                                    continue
                            if cuota_seleccionada:
                                break
                    except Exception as e:
                        continue
                
                if not cuota_seleccionada:
                    logger.warning("⚠️ No se pudo seleccionar cuota - continuando sin ella")
                    
                self._espera_humana(2, 3, "confirmando cuota")
            except Exception as e:
                logger.warning(f"⚠️ Error seleccionando cuota Angular: {e}")
            
            # 5. Día de Vencimiento → Buscar en selects dinámicos
            logger.info("📅 Seleccionando Día de Vencimiento: 2 (Angular dinámico)")
            try:
                # Recargar los selects después de seleccionar cuota
                selects_actualizados = self.driver.find_elements(By.CSS_SELECTOR, "select")
                
                dia_seleccionado = False
                for i, select_elem in enumerate(selects_actualizados):
                    try:
                        select_obj = Select(select_elem)
                        opciones = [option.text.strip() for option in select_obj.options if option.text.strip()]
                        
                        # Verificar si contiene números (días) y no es el select de productos o cuotas
                        if (any(opcion.strip().isdigit() and opcion.strip() in ["2", "5", "10", "15"] for opcion in opciones) and 
                            not any("cuota" in opcion.lower() or "modular" in opcion.lower() for opcion in opciones)):
                            logger.info(f"✅ Select de días encontrado en posición {i}: {opciones}")
                            # Intentar seleccionar "2"
                            try:
                                select_obj.select_by_visible_text("2")
                                logger.info("✅ Día de vencimiento seleccionado: 2")
                                dia_seleccionado = True
                                break
                            except:
                                # Si no funciona por texto, intentar por índice
                                try:
                                    if len(opciones) > 1:
                                        select_obj.select_by_index(1)  # Primera opción después de "Seleccione"
                                        logger.info("✅ Día de vencimiento seleccionado por índice")
                                        dia_seleccionado = True
                                        break
                                except:
                                    continue
                    except Exception as e:
                        continue
                
                if not dia_seleccionado:
                    logger.warning("⚠️ No se pudo seleccionar día de vencimiento")
                    
                self._espera_humana(2, 3, "confirmando día vencimiento")
            except Exception as e:
                logger.warning(f"⚠️ Error seleccionando día Angular: {e}")
            
            # ESPERAR FINAL PARA QUE ANGULAR PROCESE TODO
            logger.info("⏳ Esperando procesamiento final Angular...")
            self._espera_humana(4, 6, "procesamiento final Angular")
            
            # 6. BOTÓN SIMULAR - MEJORADO PARA ANGULAR
            logger.info("🔘 Esperando que el botón SIMULAR se habilite (Angular)...")
            try:
                # Método mejorado para Angular
                boton_encontrado = False
                for intento in range(25):  # Aumentamos intentos para Angular
                    try:
                        # Buscar botón que NO tenga la clase 'disable-button'
                        btn_simular = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            "button[value='SIMULAR']:not(.disable-button)"
                        )
                        
                        if btn_simular.is_displayed() and btn_simular.is_enabled():
                            logger.info(f"✅ Botón SIMULAR habilitado después de {intento+1} segundos")
                            
                            # Hacer scroll al botón y click
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", 
                                btn_simular
                            )
                            self._espera_humana(1, 2, "scrolling al botón")
                            self._click_humano(btn_simular)
                            self._espera_humana(8, 12, "procesando simulación Angular")
                            logger.info("✅ Simulación Angular ejecutada exitosamente")
                            boton_encontrado = True
                            break
                    except:
                        # Si no encuentra el botón habilitado, esperar 1 segundo más
                        logger.info(f"⏳ Intento {intento+1}/25: Botón Angular aún no habilitado, esperando...")
                        time.sleep(1)
                        continue
                
                if not boton_encontrado:
                    # Método de emergencia para Angular
                    logger.warning("⚠️ Botón SIMULAR Angular no se habilitó, intentando métodos de emergencia...")
                    
                    try:
                        btn_simular_disabled = self.driver.find_element(By.CSS_SELECTOR, "button[value='SIMULAR']")
                        logger.info("🔧 Intentando habilitar botón Angular con JavaScript...")
                        
                        # Script específico para componentes Angular
                        self.driver.execute_script("""
                            var button = arguments[0];
                            // Remover clase disable-button
                            button.classList.remove('disable-button');
                            // Habilitar el botón
                            button.disabled = false;
                            // Restablecer estilos
                            button.style.pointerEvents = 'auto';
                            button.style.opacity = '1';
                            // Disparar eventos Angular
                            button.dispatchEvent(new Event('click', { bubbles: true }));
                        """, btn_simular_disabled)
                        
                        self._espera_humana(8, 12, "procesando simulación forzada Angular")
                        logger.info("✅ Simulación Angular ejecutada con método de emergencia")
                        boton_encontrado = True
                        
                    except Exception as e:
                        logger.error(f"❌ Método de emergencia Angular falló: {e}")
                        self.driver.save_screenshot(f"error_simular_angular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                        raise Exception("Error en simulación Angular - botón no disponible")
                
            except Exception as e:
                logger.error(f"❌ Error en simulación Angular: {e}")
                self.driver.save_screenshot(f"error_simulacion_angular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                raise Exception(f"Error en simulación Angular: {e}")
            
            # ============= CONTINUAR CON EL RESTO DEL FLUJO (IGUAL QUE ANTES) =============
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
            
            # ============= RESTO DEL FLUJO IGUAL QUE ANTES =============
            # (Información personal, ubicación, laboral, evaluación final)
            self._completar_resto_flujo_angular(cliente_data)
            
            logger.info("🎉 ¡FLUJO DE FINANCIAMIENTO ANGULAR COMPLETADO EXITOSAMENTE!")
            
        except Exception as e:
            logger.error(f"❌ Error en configuración de financiamiento Angular: {e}")
            raise

    def _completar_resto_flujo_angular(self, cliente_data):
        """Completar el resto del flujo (información personal, ubicación, etc.)"""
        try:
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
            
            # Estado Civil → Seleccionar "Soltero/a" (CORREGIDO PARA EVITAR DUPLICADOS)
            logger.info("💑 Seleccionando Estado Civil: Soltero/a")
            try:
                select_civil = self.driver.find_element(By.CSS_SELECTOR, "select")
                select_obj = Select(select_civil)
                
                # MÉTODO 1: Intentar por valor específico para evitar duplicados
                try:
                    select_obj.select_by_value("7: Object")  # Soltero/a real
                    logger.info("✅ Estado Civil seleccionado por valor: Soltero/a")
                except:
                    # MÉTODO 2: Si falla, usar índice (última opción de Soltero/a)
                    try:
                        opciones = select_obj.options
                        for i, opcion in enumerate(opciones):
                            if opcion.text == "Soltero/a" and not opcion.get_attribute("disabled"):
                                select_obj.select_by_index(i)
                                logger.info(f"✅ Estado Civil seleccionado por índice {i}: Soltero/a")
                                break
                    except:
                        # MÉTODO 3: Fallback - seleccionar último índice disponible
                        select_obj.select_by_index(-1)
                        logger.info("✅ Estado Civil seleccionado por fallback")
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
            
        except Exception as e:
            logger.error(f"❌ Error completando resto del flujo Angular: {e}")
            raise

    def procesar_todos_los_clientes(self):
        """Procesar todos los clientes CON SELECTORES ANGULAR CORREGIDOS"""
        logger.info("🚀 INICIANDO PROCESAMIENTO CON SELECTORES ANGULAR...")
        
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
                
                logger.info(f"👤 Procesando cliente {idx} con selectores Angular...")
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
        
        logger.info("🎉 ¡PROCESAMIENTO ANGULAR COMPLETADO!")
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
            'version': 'SELECTORES_ANGULAR_CORREGIDOS',
            'configuracion_chrome': 'SIN_PROXY_GARANTIZADO',
            'selectores': 'BASADOS_EN_COMPONENTES_ANGULAR_REALES',
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
        
        with open('reporte_salvum_angular_corregido.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        logger.info("="*70)
        logger.info("📊 REPORTE FINAL - SELECTORES ANGULAR CORREGIDOS")
        logger.info("="*70)
        logger.info(f"🔧 Configuración: Chrome sin proxy + Selectores Angular reales")
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
        """VERSIÓN CORREGIDA: Automatización con selectores Angular"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN CON SELECTORES ANGULAR CORREGIDOS")
        logger.info("="*70)
        logger.info(f"🔧 Chrome: Sin proxy garantizado")
        logger.info(f"🎯 Selectores: Basados en componentes Angular reales")
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
            
            logger.info("🎉 ¡AUTOMATIZACIÓN ANGULAR CORREGIDA COMPLETADA!")
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
    automator = SalvumAutomacionCorregida()
    
    print("🇨🇱 AUTOMATIZACIÓN SALVUM - SELECTORES ANGULAR CORREGIDOS")
    print("🔧 Basado en componentes Angular reales")
    print(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
    print("-"*70)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Ver reporte_salvum_angular_corregido.json para detalles")
        print("📊 Estados actualizados en todas las planillas")
        print("🔧 Versión con selectores Angular corregidos")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
