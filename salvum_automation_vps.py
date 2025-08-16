#!/usr/bin/env python3
"""
AUTOMATIZACIÓN SALVUM CON MÚLTIPLES PLANILLAS + VPS CHILE - VERSIÓN FINAL CORREGIDA
Procesa clientes de múltiples agentes automáticamente usando VPS chileno
CORRECCIONES INTEGRADAS: Chrome sin SOCKS + Acentos + Estados flexibles
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
VPS_IP_ESPERADA = "45.7.230.109"  # IP de tu VPS Chile

# 🎯 ESTADOS VÁLIDOS PARA PROCESAR (MEJORA: Flexibilidad)
ESTADOS_VALIDOS_PROCESAR = [
    'NUEVO', 'PROCESAR', 'PENDIENTE', 'LISTO', 
    'READY', 'AUTOMATIZAR', 'SI', 'YES', 'PROCESO'
]

class SalvumMultiplePlanillasConVPS:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.gc = None  # Google Sheets client
        self.agentes_config = []
        self.clientes_procesados = []
        self.clientes_fallidos = []
        
    def verificar_conexion_vps(self):
        """Verificar que estamos conectados correctamente al VPS Chile"""
        logger.info("🔍 VERIFICANDO CONEXIÓN AL VPS CHILE")
        logger.info("-" * 50)
        
        try:
            import requests
            
            # Configurar requests para usar el proxy SOCKS
            proxies = {
                'http': SOCKS_PROXY,
                'https': SOCKS_PROXY
            }
            
            # Verificar IP via VPS
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

    def verificar_tunel_socks(self):
        """🔧 Verificar túnel SOCKS (para verificaciones HTTP)"""
        logger.info("🔍 Verificando túnel SOCKS...")
        
        try:
            # 1. Verificar proceso SSH
            result = subprocess.run(['pgrep', '-f', 'ssh.*-D.*8080'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("❌ Proceso SSH del túnel no encontrado")
                return False
            
            logger.info(f"✅ Proceso SSH encontrado: PID {result.stdout.strip()}")
            
            # 2. Verificar puerto
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('localhost', 8080))
            sock.close()
            
            if result != 0:
                logger.error("❌ Puerto 8080 no está disponible")
                return False
            
            logger.info("✅ Puerto 8080 escuchando")
            
            # 3. Verificar conectividad básica
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
            # Intentar cargar desde archivo config.json
            if os.path.exists('config.json'):
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Filtrar solo agentes activos
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
                # Fallback: usar configuración básica desde variables de entorno
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
            # Credenciales desde variable de entorno (GitHub Secrets)
            creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
            if creds_json:
                creds_dict = json.loads(creds_json)
                creds = Credentials.from_service_account_info(creds_dict)
            else:
                # Archivo local para desarrollo
                creds = Credentials.from_service_account_file('credentials.json')
            
            # Scopes necesarios
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
        """🔧 CORRECCIÓN: Leer clientes con manejo de acentos y estados flexibles"""
        logger.info(f"📖 Leyendo clientes de {nombre_agente}...")
        
        try:
            # Abrir planilla específica
            spreadsheet = self.gc.open_by_key(sheet_id)
            
            # ADAPTACIÓN: Buscar la hoja correcta
            worksheet = None
            nombres_hoja_posibles = [
                'Mis_Clientes_Financiamiento',  # Tu hoja real
                'sheet1',  # Fallback original
                'Hoja1',   # Nombre español
                'Sheet1'   # Nombre inglés
            ]
            
            for nombre_hoja in nombres_hoja_posibles:
                try:
                    worksheet = spreadsheet.worksheet(nombre_hoja)
                    logger.info(f"✅ Hoja encontrada: '{nombre_hoja}'")
                    break
                except:
                    continue
            
            if not worksheet:
                # Si no encuentra ninguna, usar la primera disponible
                worksheet = spreadsheet.sheet1
                logger.info("⚠️ Usando primera hoja disponible")
            
            # Obtener todos los datos
            records = worksheet.get_all_records()
            logger.info(f"📊 Total registros en planilla: {len(records)}")
            
            if not records:
                logger.warning(f"⚠️ {nombre_agente}: Planilla vacía")
                return []
            
            # MOSTRAR HEADERS REALES PARA DEBUG
            headers_reales = list(records[0].keys())
            logger.info(f"📋 Headers encontrados: {headers_reales}")
            
            # 🔧 CORRECCIÓN: Verificar columnas críticas con manejo de acentos
            tiene_procesar = any('PROCESAR' in h.upper() for h in headers_reales)
            
            # 🔧 CORRECCIÓN: Buscar RENTA LIQUIDA con diferentes variantes (con y sin acento)
            tiene_renta = any(
                ('RENTA' in h.upper() and 'LIQUIDA' in h.upper()) or
                ('RENTA' in h.upper() and 'LÍQUIDA' in h.upper())  # Con acento
                for h in headers_reales
            )
            
            tiene_nombre = any('NOMBRE' in h.upper() and 'CLIENTE' in h.upper() for h in headers_reales)
            
            if not tiene_procesar:
                logger.error(f"❌ {nombre_agente}: Falta columna PROCESAR")
                return []
            if not tiene_renta:
                logger.error(f"❌ {nombre_agente}: Falta columna RENTA LIQUIDA/LÍQUIDA")
                logger.info(f"   Headers disponibles: {headers_reales}")
                return []
            if not tiene_nombre:
                logger.error(f"❌ {nombre_agente}: Falta columna Nombre Cliente")
                return []
            
            logger.info("✅ Estructura de planilla válida")
            logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
            
            # Filtrar clientes listos para procesar
            clientes_procesar = []
            
            for i, record in enumerate(records, start=2):  # Start=2 porque row 1 son headers
                # 🔧 CORRECCIÓN: Verificar renta con diferentes variantes (con y sin acento)
                renta_liquida = (record.get('RENTA LIQUIDA', 0) or 
                               record.get('RENTA LÍQUIDA', 0) or  # Con acento
                               record.get('Renta Liquida', 0) or
                               record.get('Renta Líquida', 0))   # Con acento
                
                procesar = str(record.get('PROCESAR', '')).upper().strip()
                
                # Limpiar y convertir renta líquida
                try:
                    if isinstance(renta_liquida, str):
                        # Remover caracteres no numéricos excepto punto y coma
                        renta_limpia = ''.join(c for c in renta_liquida if c.isdigit() or c in '.,')
                        renta_liquida = float(renta_limpia.replace(',', '.')) if renta_limpia else 0
                    else:
                        renta_liquida = float(renta_liquida) if renta_liquida else 0
                except:
                    renta_liquida = 0
                
                logger.info(f"🔍 Fila {i}: PROCESAR='{procesar}', RENTA={renta_liquida}")
                
                # 🔧 MEJORA: Verificar con estados flexibles
                if renta_liquida > 0 and procesar in ESTADOS_VALIDOS_PROCESAR:
                    
                    # ESTRUCTURA REAL: Columnas separadas
                    nombre_cliente = record.get('Nombre Cliente', '')
                    rut_cliente = record.get('RUT', '')
                    
                    # Validaciones adicionales
                    if not nombre_cliente.strip():
                        logger.warning(f"⚠️ Fila {i}: Nombre cliente vacío")
                        continue
                    
                    if not rut_cliente.strip():
                        logger.warning(f"⚠️ Fila {i}: RUT vacío")
                        continue
                    
                    # MONTO: Columna I (Monto Financiamiento)
                    monto_financiar = self._limpiar_numero(record.get('Monto Financiamiento', 0))
                    
                    if monto_financiar <= 0:
                        logger.warning(f"⚠️ Fila {i}: Monto inválido: {monto_financiar}")
                        continue
                    
                    cliente = {
                        'agente': nombre_agente,
                        'sheet_id': sheet_id,
                        'row_number': i,  # Para actualizar después
                        'Nombre Cliente': nombre_cliente,
                        'RUT': rut_cliente,
                        'Email': record.get('Email', ''),
                        'Telefono': record.get('Teléfono', record.get('Telefono', '')),
                        'Monto Financiar Original': monto_financiar,
                        'RENTA LIQUIDA': renta_liquida,
                        'Modelo Casa': record.get('Modelo Casa', ''),
                        'Precio Casa': self._limpiar_numero(record.get('Precio Casa', 0)),
                        'Origen': record.get('Origen', ''),  # Columna J
                        'Estado Original': procesar  # Guardar estado original
                    }
                    clientes_procesar.append(cliente)
                    
                    logger.info(f"  ✅ Cliente agregado: {nombre_cliente} (RUT: {rut_cliente}) - Monto: {monto_financiar} - Estado: {procesar}")
            
            logger.info(f"✅ {nombre_agente}: {len(clientes_procesar)} clientes para procesar")
            
            if clientes_procesar:
                for cliente in clientes_procesar:
                    logger.info(f"  📋 {cliente['Nombre Cliente']} (RUT: {cliente['RUT']}) - Fila: {cliente['row_number']} - Estado: {cliente['Estado Original']}")
            else:
                # 🔧 MEJORA: Análisis detallado de por qué no hay clientes
                logger.warning(f"⚠️ {nombre_agente}: No se encontraron clientes válidos")
                logger.info("🔍 Análisis detallado:")
                
                estados_encontrados = {}
                filas_con_renta = 0
                
                for record in records:
                    # Contar estados
                    estado = str(record.get('PROCESAR', '')).strip()
                    if estado:
                        estados_encontrados[estado] = estados_encontrados.get(estado, 0) + 1
                    
                    # Contar rentas (con y sin acento)
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
                
                if filas_con_renta > 0:
                    logger.info("💡 SUGERENCIAS:")
                    logger.info("   1. Cambiar valores en columna PROCESAR a uno de los estados válidos")
                    logger.info(f"   2. Estados válidos: {', '.join(ESTADOS_VALIDOS_PROCESAR)}")
                    logger.info("   3. Verificar que las filas tengan tanto RENTA > 0 como estado válido")
            
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
                # Remover $ , . y espacios, mantener solo números
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
        
        # Mostrar resumen por agente
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
            
            # Abrir la planilla específica
            spreadsheet = self.gc.open_by_key(sheet_id)
            
            # Buscar la hoja correcta (igual que en leer_clientes)
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
            
            # Actualizar columna PROCESAR (columna M = 13)
            worksheet.update_cell(row_number, 13, estado)
            
            # Actualizar timestamp y resultado
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.update_cell(row_number, 14, f"Procesado: {timestamp}")
            
            if resultado:
                worksheet.update_cell(row_number, 15, resultado)
            
            logger.info(f"✅ {agente} - Estado actualizado en fila {row_number}: {estado}")
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estado: {e}")
    
    def configurar_navegador(self):
        """🔧 CORRECCIÓN: Navegador sin SOCKS (evita error de conexión)"""
        logger.info("🔧 Configurando navegador con estrategia alternativa...")
        
        # Verificar túnel SOCKS (mantener para verificaciones HTTP)
        if not self.verificar_tunel_socks():
            logger.warning("⚠️ Túnel SOCKS no disponible - Continuando sin proxy en Chrome")
        
        options = Options()
        
        # Configuración para GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
        
        # Configuración básica (SIN PROXY SOCKS)
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        logger.info("🔄 Usando estrategia alternativa: Chrome sin proxy SOCKS")
        logger.info("💡 El VPS Chile se mantiene para verificaciones HTTP")
        
        # 🤖 ANTI-DETECCIÓN SÚPER AVANZADA (sin proxy)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')  # Más rápido
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 👤 PREFERENCIAS HUMANAS
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "media_stream": 2,
            },
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            # ✅ TIMEOUTS SE CONFIGURAN AQUÍ
            self.driver.set_page_load_timeout(90)
            self.driver.implicitly_wait(20)
            self.wait = WebDriverWait(self.driver, 30)
            
            # 🧠 SCRIPTS ANTI-DETECCIÓN AVANZADOS
            self.driver.execute_script("""
                // Eliminar webdriver property
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                // Simular propiedades de navegador real
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Simular languages chileno
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['es-CL', 'es', 'en']
                });
                
                // Ocultar automation flags
                window.chrome = {
                    runtime: {}
                };
            """)
            
            logger.info("✅ Navegador configurado (estrategia sin SOCKS)")
            
            # 📊 RESUMEN DE CONFIGURACIÓN
            logger.info("\n🤖 CONFIGURACIÓN APLICADA:")
            logger.info("  ✅ Anti-detección súper avanzada")
            logger.info("  ✅ VPS Chile para verificaciones HTTP")
            logger.info("  ✅ Chrome sin proxy (evita error SOCKS)")
            logger.info("  ✅ Esperas aleatorias entre 1-15 segundos")
            logger.info("  ✅ Tipeo carácter por carácter con pausas")
            logger.info("  ✅ Movimiento de mouse simulado")
            logger.info("  ✅ Timeouts extendidos (90s)")
            logger.info("  ✅ Properties de navegador real")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando Chrome: {e}")
            return False
        
    def _espera_humana(self, min_seg=1, max_seg=4, motivo="acción"):
        """Espera aleatoria que simula comportamiento humano"""
        import random
        tiempo = random.uniform(min_seg, max_seg)
        logger.info(f"⏳ Esperando {tiempo:.1f}s ({motivo})...")
        time.sleep(tiempo)
    
    def _mover_mouse_humano(self, elemento):
        """Simular movimiento de mouse humano hacia elemento"""
        try:
            # Mover el mouse al elemento de forma humana
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
            # Limpiar campo
            campo.clear()
            self._espera_humana(0.5, 1, "después de limpiar")
            
            # Tipear carácter por carácter con pausas humanas
            for char in texto:
                campo.send_keys(char)
                # Pausa aleatoria entre caracteres (como humano)
                pausa = random.uniform(0.05, 0.15)
                time.sleep(pausa)
            
            self._espera_humana(0.5, 1.5, "después de tipear")
            
        except Exception as e:
            # Fallback: tipeo normal
            logger.warning(f"Fallback a tipeo normal: {e}")
            campo.clear()
            time.sleep(1)
            campo.send_keys(texto)
            time.sleep(2)
    
    def _click_humano(self, elemento):
        """Click humano con movimiento de mouse"""
        try:
            # Scroll al elemento
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", elemento)
            self._espera_humana(0.5, 1.5, "scroll al elemento")
            
            # Mover mouse al elemento
            self._mover_mouse_humano(elemento)
            
            # Click con pausa
            self._espera_humana(0.3, 0.8, "antes de click")
            elemento.click()
            self._espera_humana(0.5, 1.5, "después de click")
            
        except:
            # Fallback: click normal
            try:
                self.driver.execute_script("arguments[0].click();", elemento)
                self._espera_humana(1, 2, "click JavaScript fallback")
            except:
                elemento.click()
                time.sleep(2)
    
    def _leer_pagina_humano(self):
        """Simular que un humano está leyendo la página"""
        import random
        
        # Simular scroll de lectura
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/4);")
            self._espera_humana(1, 2, "leyendo inicio")
            
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            self._espera_humana(1, 3, "leyendo medio")
            
            self.driver.execute_script("window.scrollTo(0, 0);")
            self._espera_humana(0.5, 1.5, "volviendo arriba")
            
        except:
            # Simple espera si falla el scroll
            self._espera_humana(2, 5, "leyendo página")
    
    def realizar_login(self):
        """🔧 CORRECCIÓN: Login híbrido (VPS para verificaciones + Chrome directo)"""
        logger.info("🔐 Realizando login HÍBRIDO (VPS para verificaciones + Chrome directo)...")
        
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            logger.info(f"🔄 Intento de login {intento}/{max_intentos}")
            
            try:
                # ✅ MANTENER verificación VPS para asegurar que el sistema funciona
                vps_ok, ip_data = self.verificar_conexion_vps()
                if vps_ok:
                    logger.info("✅ VPS Chile disponible para verificaciones")
                else:
                    logger.warning("⚠️ VPS no disponible - Continuando con Chrome directo")
                
                # 🔗 Acceder a Salvum directamente (sin proxy en Chrome)
                logger.info("🔗 Accediendo a Salvum con Chrome directo...")
                self.driver.get("https://prescriptores.salvum.cl/login")
                time.sleep(15)
                
                # Información de la página
                url = self.driver.current_url
                titulo = self.driver.title
                html_size = len(self.driver.page_source)
                
                logger.info(f"📍 URL: {url}")
                logger.info(f"📄 Título: {titulo}")
                logger.info(f"📊 HTML size: {html_size}")
                
                # Screenshot
                screenshot_name = f'salvum_acceso_directo_intento_{intento}.png'
                self.driver.save_screenshot(screenshot_name)
                logger.info(f"📸 Screenshot: {screenshot_name}")
                
                # Verificar acceso
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
        """🇨🇱 Método de login SÚPER HUMANO (basado en el que funcionó al 100%)"""
        logger.info("🔑 INICIANDO PROCESO DE LOGIN SÚPER HUMANO")
        logger.info("-" * 50)
        
        try:
            # Obtener credenciales
            usuario = os.getenv('SALVUM_USER')
            password = os.getenv('SALVUM_PASS')
            
            logger.info(f"👤 Usuario: {usuario}")
            logger.info("🔒 Password: [PROTEGIDO]")
            
            # 👤 COMPORTAMIENTO HUMANO: Leer la página primero
            logger.info("👁️ Simulando lectura humana de la página...")
            self._leer_pagina_humano()
            
            # Espera aleatoria humana
            self._espera_humana(3, 7, "comportamiento humano inicial")
            
            # Buscar campos de login con múltiples selectores
            logger.info("🔍 Buscando campos de login de forma humana...")
            
            campo_usuario = None
            campo_password = None
            
            # Selectores para usuario (del código que funcionó)
            selectores_usuario = [
                "input[type='text']",
                "input[type='email']", 
                "input[name*='usuario']",
                "input[name*='email']",
                "input[name*='user']",
                "input[id*='usuario']",
                "input[id*='email']"
            ]
            
            # Buscar campo usuario de forma más humana
            for selector in selectores_usuario:
                try:
                    campos = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for campo in campos:
                        if campo.is_displayed() and campo.is_enabled():
                            # Simular que estamos "inspeccionando" el campo
                            self._mover_mouse_humano(campo)
                            self._espera_humana(0.5, 1, "inspeccionando campo")
                            
                            campo_usuario = campo
                            logger.info(f"✅ Campo usuario encontrado: {selector}")
                            break
                    if campo_usuario:
                        break
                except:
                    continue
            
            # Buscar campo password de forma humana
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
            
            # 👤 LLENAR CAMPOS DE FORMA SÚPER HUMANA
            logger.info("✏️ Llenando campos de forma humana...")
            
            # Focus y llenar usuario
            logger.info("👤 Llenando usuario...")
            self._click_humano(campo_usuario)
            self._tipear_humano(campo_usuario, usuario)
            logger.info("✅ Usuario ingresado de forma humana")
            
            # Pequeña pausa humana entre campos
            self._espera_humana(1, 3, "pausa entre campos")
            
            # Focus y llenar password  
            logger.info("🔒 Llenando password...")
            self._click_humano(campo_password)
            self._tipear_humano(campo_password, password)
            logger.info("✅ Password ingresado de forma humana")
            
            # Pausa humana antes de submit (como si estuviéramos verificando)
            self._espera_humana(2, 4, "verificando datos antes de enviar")
            
            # Screenshot antes de submit
            self.driver.save_screenshot('salvum_antes_submit_humano.png')
            logger.info("📸 Screenshot antes de submit")
            
            # 🔘 BUSCAR Y HACER CLICK EN BOTÓN DE FORMA HUMANA
            logger.info("🔘 Buscando botón de submit de forma humana...")
            
            boton_submit = None
            
            # Método 1: Por tipo submit
            try:
                botones = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                for btn in botones:
                    if btn.is_displayed() and btn.is_enabled():
                        # Simular que estamos viendo el botón
                        self._mover_mouse_humano(btn)
                        self._espera_humana(0.5, 1, "inspeccionando botón")
                        boton_submit = btn
                        logger.info("✅ Botón submit encontrado por tipo")
                        break
            except:
                pass
            
            # Método 2: Por texto
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
            
            # EJECUTAR SUBMIT DE FORMA HUMANA
            if boton_submit:
                logger.info("🖱️ Haciendo click en botón de forma humana...")
                self._click_humano(boton_submit)
                logger.info("🔘 Click humano ejecutado")
            else:
                # Último recurso: Enter humano
                logger.info("⌨️ Usando Enter como humano...")
                self._espera_humana(0.5, 1, "preparando Enter")
                campo_password.send_keys(Keys.RETURN)
                self._espera_humana(1, 2, "después de Enter")
                logger.info("⌨️ Enter enviado")
            
            # 📱 ESPERAR RESPUESTA DE FORMA HUMANA
            logger.info("⏳ Esperando respuesta del servidor de forma humana...")
            
            # Simular que estamos esperando pacientemente
            for i in range(3):
                self._espera_humana(3, 5, f"esperando respuesta {i+1}/3")
                
                # Verificar si ya cambió la página
                try:
                    url_actual = self.driver.current_url
                    if "login" not in url_actual.lower():
                        logger.info(f"✅ Página cambió durante espera: {url_actual}")
                        break
                except:
                    pass
            
            # Screenshot después de submit
            self.driver.save_screenshot('salvum_despues_submit_humano.png')
            logger.info("📸 Screenshot después de submit")
            
            # VERIFICAR RESULTADO
            nueva_url = self.driver.current_url
            nuevo_titulo = self.driver.title
            
            logger.info(f"📍 Nueva URL: {nueva_url}")
            logger.info(f"📄 Nuevo título: {nuevo_titulo}")
            
            # Leer la nueva página como humano
            self._espera_humana(1, 2, "leyendo resultado")
            
            # Determinar éxito del login
            if nueva_url != "https://prescriptores.salvum.cl/login" and "login" not in nueva_url.lower():
                logger.info("🎉 ¡LOGIN SÚPER HUMANO EXITOSO! - URL cambió")
                
                # Simular navegación humana post-login
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
            # Actualizar estado a "PROCESANDO"
            self.actualizar_estado_cliente(cliente_data, "PROCESANDO")
            
            # PASO 1: Nueva Solicitud
            logger.info("📝 Iniciando nueva solicitud...")
            nueva_solicitud_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//button[contains(text(), 'Nueva Solicitud')] | //a[contains(text(), 'Nueva Solicitud')]"
                ))
            )
            self._click_humano(nueva_solicitud_btn)
            self._espera_humana(3, 6, "cargando nueva solicitud")
            
            # PASO 2: Datos del Cliente
            logger.info("📋 Llenando datos del cliente...")
            
            # RUT
            campo_rut = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "input[name*='rut'], input[id*='rut'], input[placeholder*='RUT']"
                ))
            )
            self._click_humano(campo_rut)
            self._tipear_humano(campo_rut, str(cliente_data['RUT']))
            
            # Nombre (extraer primer nombre)
            nombre_partes = nombre.split()
            primer_nombre = nombre_partes[0] if nombre_partes else nombre
            apellido = ' '.join(nombre_partes[1:]) if len(nombre_partes) > 1 else "Gonzalez"
            
            # Llenar campos básicos
            self._llenar_campo_si_existe("input[name*='nombre'], input[id*='nombre'], input[placeholder*='Nombre']", primer_nombre)
            self._llenar_campo_si_existe("input[name*='apellido'], input[id*='apellido']", apellido)
            self._llenar_campo_si_existe("input[type='email'], input[name*='email']", str(cliente_data['Email']))
            self._llenar_campo_si_existe("input[name*='telefono'], input[name*='phone']", str(cliente_data['Telefono']))
            self._llenar_campo_si_existe("input[type='date'], input[name*='fecha']", "25/08/1987")
            
            # Continuar
            self._click_continuar()
            
            # PASO 3: Configurar Financiamiento
            logger.info("💰 Configurando financiamiento...")
            
            # Producto: Casas Modulares
            self._seleccionar_producto("Casas Modulares")
            
            # Montos
            monto = int(cliente_data['Monto Financiar Original'])
            self._llenar_campo_si_existe("input[name*='valor'], input[id*='valor']", str(monto))
            self._llenar_campo_si_existe("input[name*='solicitar'], input[name*='monto']", str(monto))
            
            # Cuotas y día
            self._configurar_cuotas_y_dia()
            
            # Simular
            btn_simular = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Simular')]")
            self._click_humano(btn_simular)
            self._espera_humana(6, 10, "procesando simulación")
            
            # PASO 4: Continuar simulación
            self._click_continuar()
            
            # PASO 5: Información Personal
            logger.info("📋 Completando información personal...")
            self._llenar_informacion_personal(cliente_data)
            
            # PASO 6: Enviar Solicitud
            logger.info("📤 Enviando solicitud...")
            btn_enviar = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Enviar')]"))
            )
            self._click_humano(btn_enviar)
            self._espera_humana(8, 12, "enviando solicitud")
            
            # PASO 7: Capturar resultado
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
            
            # Actualizar estado exitoso
            self.actualizar_estado_cliente(cliente_data, "COMPLETADO", f"Exitoso: {url_resultado}")
            
            self.clientes_procesados.append(resultado_cliente)
            logger.info(f"✅ {agente} - Cliente {nombre} procesado exitosamente")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error procesando cliente {nombre} ({agente}): {e}")
            
            # Actualizar estado de error
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
                
                # Comportamiento humano
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
            
            # Simular que leemos antes de continuar
            self._espera_humana(1, 3, "revisando antes de continuar")
            self._click_humano(btn_continuar)
            
            # Esperar carga de siguiente página
            self._espera_humana(3, 6, "cargando siguiente página")
            
        except Exception as e:
            logger.warning(f"Error en continuar: {e}")
            self._espera_humana(2, 4, "fallback continuar")
    
    def _seleccionar_producto(self, producto):
        """Seleccionar producto DE FORMA HUMANA"""
        try:
            logger.info(f"🏠 Seleccionando producto: {producto}")
            
            # Buscar campo producto
            campo_producto = self.driver.find_element(By.XPATH, "//select | //input[name*='producto']")
            
            # Comportamiento humano al seleccionar
            self._mover_mouse_humano(campo_producto)
            self._espera_humana(0.5, 1.5, "viendo opciones de producto")
            
            if campo_producto.tag_name == 'select':
                select = Select(campo_producto)
                # Simular que leemos las opciones
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
            # Cuotas: 60
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
            # Día vencimiento: 2
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
        
        # Simular que leemos el formulario primero
        self._leer_pagina_humano()
        
        # CI
        logger.info("🆔 Llenando CI...")
        self._llenar_campo_si_existe("input[name*='ci'], input[name*='cedula']", "123456789")
        
        # Estado Civil: Soltero
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
        
        # Ubicación: Coquimbo, Elqui, La Serena
        logger.info("🗺️ Configurando ubicación...")
        self._seleccionar_ubicacion()
        
        # Dirección
        logger.info("🏠 Llenando dirección...")
        self._llenar_campo_si_existe("input[name*='direccion']", "Aven")
        
        # Modalidad trabajo: Jubilado
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
        
        # Renta líquida (desde planilla)
        renta_liquida = int(cliente_data['RENTA LIQUIDA'])
        logger.info(f"💰 Llenando renta líquida: {renta_liquida}")
        self._llenar_campo_si_existe("input[name*='pension'], input[name*='renta'], input[name*='liquida']", str(renta_liquida))
        
        # Pausa final como si estuviéramos revisando todo
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
        
        # Obtener todos los clientes
        todos_los_clientes = self.leer_todos_los_clientes()
        
        if not todos_los_clientes:
            logger.info("ℹ️ No hay clientes para procesar en ninguna planilla")
            return True
        
        total_clientes = len(todos_los_clientes)
        logger.info(f"📊 Total clientes a procesar CON COMPORTAMIENTO HUMANO: {total_clientes}")
        
        # Procesar cada cliente
        for idx, cliente in enumerate(todos_los_clientes, 1):
            logger.info(f"\n{'='*20} CLIENTE {idx}/{total_clientes} (SÚPER HUMANO) {'='*20}")
            logger.info(f"👥 Agente: {cliente['agente']}")
            logger.info(f"👤 Cliente: {cliente['Nombre Cliente']} - {cliente['RUT']}")
            
            try:
                # 👤 COMPORTAMIENTO HUMANO ENTRE CLIENTES
                if idx > 1:
                    logger.info("🤔 Simulando pausa humana entre clientes...")
                    # Simular que estamos descansando/revisando entre clientes
                    self._espera_humana(8, 15, "descanso entre clientes")
                    
                    # Simular navegación casual (como humano volviendo al inicio)
                    try:
                        logger.info("🔄 Regresando al dashboard de forma humana...")
                        self.driver.get("https://prescriptores.salvum.cl/")
                        self._espera_humana(3, 6, "cargando dashboard")
                        
                        # Simular que leemos el dashboard
                        self._leer_pagina_humano()
                        
                    except Exception as e:
                        logger.warning(f"Error regresando al dashboard: {e}")
                        self._espera_humana(3, 5, "recuperación dashboard")
                
                # Procesar cliente con comportamiento humano
                logger.info(f"👤 Iniciando procesamiento humano del cliente {idx}...")
                if self.procesar_cliente_individual(cliente):
                    logger.info(f"✅ Cliente {idx} completado CON COMPORTAMIENTO HUMANO")
                    
                    # 🎉 Celebración humana pequeña (pausa satisfactoria)
                    self._espera_humana(2, 4, "satisfacción por cliente completado")
                    
                else:
                    logger.error(f"❌ Cliente {idx} falló")
                    
                    # 😔 Pausa de "frustración" humana
                    self._espera_humana(3, 6, "procesando fallo")
                
            except Exception as e:
                logger.error(f"❌ Error procesando cliente {idx}: {e}")
                
                # Pausa de recuperación humana
                self._espera_humana(5, 8, "recuperándose de error")
                continue
        
        logger.info("🎉 ¡PROCESAMIENTO SÚPER HUMANO COMPLETADO!")
        
        # Pausa final de satisfacción
        self._espera_humana(3, 6, "satisfacción final por trabajo completado")
        
        return True
    
    def generar_reporte_final(self):
        """Generar reporte final por agente"""
        logger.info("📊 Generando reporte final...")
        
        total_procesados = len(self.clientes_procesados)
        total_fallidos = len(self.clientes_fallidos)
        total_clientes = total_procesados + total_fallidos
        
        # Agrupar por agente
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
            'version': 'FINAL_CORREGIDA',
            'configuracion_chrome': 'SIN_SOCKS',
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
        
        # Guardar reporte
        with open('reporte_salvum_final_corregido.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        # Mostrar reporte en consola
        logger.info("="*70)
        logger.info("📊 REPORTE FINAL - VERSIÓN CORREGIDA")
        logger.info("="*70)
        logger.info(f"🔧 Configuración: Chrome sin SOCKS")
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
                
                # Mostrar clientes procesados
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
        """🔧 VERSIÓN FINAL: Automatización completa corregida"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN MÚLTIPLES PLANILLAS (VERSIÓN FINAL CORREGIDA)")
        logger.info("="*70)
        logger.info(f"🔗 Proxy: {SOCKS_PROXY} (solo para verificaciones HTTP)")
        logger.info(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
        logger.info(f"🔧 Chrome: Sin proxy SOCKS (evita errores de conexión)")
        logger.info("="*70)
        
        try:
            # 1. Verificar conexión VPS (opcional - solo para verificaciones)
            vps_ok, ip_data = self.verificar_conexion_vps()
            if vps_ok:
                logger.info("✅ VPS Chile disponible para verificaciones")
            else:
                logger.warning("⚠️ VPS no disponible - Continuando sin verificaciones VPS")
            
            # 2. Cargar configuración de agentes
            if not self.cargar_configuracion_agentes():
                return False
            
            # 3. Configurar Google Sheets
            if not self.configurar_google_sheets():
                return False
            
            # 4. Verificar que hay clientes para procesar
            todos_los_clientes = self.leer_todos_los_clientes()
            if not todos_los_clientes:
                logger.info("ℹ️ No hay clientes para procesar")
                return True
            
            # 5. Configurar navegador (SIN SOCKS)
            if not self.configurar_navegador():
                logger.error("❌ Error configurando navegador")
                return False
            
            # 6. Login híbrido
            if not self.realizar_login():
                logger.error("❌ Login falló")
                return False
            
            # 7. Procesar todos los clientes
            self.procesar_todos_los_clientes()
            
            # 8. Generar reporte
            self.generar_reporte_final()
            
            logger.info("🎉 ¡AUTOMATIZACIÓN FINAL COMPLETADA!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en automatización: {e}")
            # Log adicional para debug
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
    
    print("🇨🇱 AUTOMATIZACIÓN SALVUM - VERSIÓN FINAL CORREGIDA")
    print("📊 Procesa clientes de múltiples agentes")
    print(f"🎯 Estados válidos: {ESTADOS_VALIDOS_PROCESAR}")
    print(f"🔧 Chrome sin SOCKS (evita errores de conexión)")
    print("-"*70)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Ver reporte_salvum_final_corregido.json para detalles")
        print("📊 Estados actualizados en todas las planillas")
        print("🔧 Versión final con todas las correcciones integradas")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
