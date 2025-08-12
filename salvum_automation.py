#!/usr/bin/env python3
"""
AUTOMATIZACIÓN SALVUM CON MÚLTIPLES PLANILLAS GOOGLE SHEETS
Procesa clientes de múltiples agentes automáticamente
"""
import os
import time
import json
import logging
import gspread
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

class SalvumMultiplePlanillas:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.gc = None  # Google Sheets client
        self.agentes_config = []
        self.clientes_procesados = []
        self.clientes_fallidos = []
        
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
        """Leer clientes de una planilla específica"""
        logger.info(f"📖 Leyendo clientes de {nombre_agente}...")
        
        try:
            # Abrir planilla específica
            worksheet = self.gc.open_by_key(sheet_id).sheet1
            
            # Obtener todos los datos
            records = worksheet.get_all_records()
            
            # Filtrar clientes listos para procesar
            clientes_procesar = []
            
            for i, record in enumerate(records, start=2):  # Start=2 porque row 1 son headers
                # Verificar condiciones
                renta_liquida = record.get('RENTA LIQUIDA', 0)
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
                
                # Verificar si está listo para procesar
                if renta_liquida > 0 and procesar == 'NUEVO':
                    cliente = {
                        'agente': nombre_agente,
                        'sheet_id': sheet_id,
                        'row_number': i,  # Para actualizar después
                        'Nombre Cliente': record.get('Nombre Cliente', ''),
                        'RUT': record.get('RUT', ''),
                        'Email': record.get('Email', ''),
                        'Telefono': record.get('Teléfono', record.get('Telefono', '')),
                        'Monto Financiar Original': self._limpiar_numero(record.get('Monto Financia Origen', 0)),
                        'RENTA LIQUIDA': renta_liquida,
                        'Modelo Casa': record.get('Modelo Casa', ''),
                        'Precio Casa': self._limpiar_numero(record.get('Precio Casa', 0))
                    }
                    clientes_procesar.append(cliente)
            
            logger.info(f"✅ {nombre_agente}: {len(clientes_procesar)} clientes para procesar")
            
            if clientes_procesar:
                for cliente in clientes_procesar:
                    logger.info(f"  📋 {cliente['Nombre Cliente']} (RUT: {cliente['RUT']}) - Fila: {cliente['row_number']}")
            
            return clientes_procesar
            
        except Exception as e:
            logger.error(f"❌ Error leyendo planilla de {nombre_agente}: {e}")
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
            worksheet = self.gc.open_by_key(sheet_id).sheet1
            
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
        """Configurar navegador optimizado con anti-detección"""
        logger.info("🔧 Configurando navegador...")
        
        options = Options()
        
        # Configuración para GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
        
        # Optimizaciones anti-detección (del código que funcionó)
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--remote-debugging-port=9222')  # NUEVO: del código que funcionó
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Configurar timeouts (del código que funcionó)
        self.driver.set_page_load_timeout(30)
        self.wait = WebDriverWait(self.driver, 20)
        
        # Scripts anti-detección
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("✅ Navegador configurado")
    
    def realizar_login(self):
        """Login robusto en Salvum basado en código que funcionó"""
        logger.info("🔐 Realizando login en Salvum...")
        
        try:
            # Verificar IP (del código que funcionó)
            logger.info("🌐 Verificando IP de GitHub Actions...")
            try:
                import requests
                ip_info = requests.get('https://ipinfo.io/json', timeout=10).json()
                logger.info(f"📍 IP: {ip_info.get('ip')}")
                logger.info(f"🏙️ Ciudad: {ip_info.get('city')}")
                logger.info(f"🏢 País: {ip_info.get('country')}")
            except:
                logger.info("⚠️ No se pudo obtener info de IP")
            
            # Acceder a página de login
            self.driver.get("https://prescriptores.salvum.cl/login")
            
            # Esperar carga completa (del código que funcionó)
            logger.info("⏳ Esperando carga completa...")
            time.sleep(15)  # Espera más larga como en el código que funcionó
            
            # Información de la página
            url = self.driver.current_url
            titulo = self.driver.title
            html_size = len(self.driver.page_source)
            
            logger.info(f"📍 URL: {url}")
            logger.info(f"📄 Título: {titulo}")
            logger.info(f"📊 HTML size: {html_size}")
            
            # Screenshot inicial
            self.driver.save_screenshot('salvum_pagina_inicial.png')
            logger.info("📸 Screenshot inicial guardado")
            
            # Verificar si llegamos a la página correcta
            page_source = self.driver.page_source.lower()
            
            if "bbva" in titulo.lower():
                logger.error("❌ BLOQUEADO - Redirigido a BBVA")
                return False
            elif html_size < 5000:
                logger.error("❌ BLOQUEADO - Página muy pequeña")
                return False
            elif "salvum" in page_source or "usuario" in page_source or "login" in page_source:
                logger.info("✅ ACCESO EXITOSO - Página de Salvum detectada!")
                
                # Llamar método de login mejorado
                return self._realizar_login_mejorado()
            else:
                logger.warning("❓ Estado desconocido de página")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error general en login: {e}")
            return False
    
    def _realizar_login_mejorado(self):
        """Método de login basado exactamente en el código que funcionó"""
        logger.info("🔑 INICIANDO PROCESO DE LOGIN MEJORADO")
        logger.info("-" * 50)
        
        try:
            # Obtener credenciales
            usuario = os.getenv('SALVUM_USER', 'Molivaco')
            password = os.getenv('SALVUM_PASS', 'd6r4YaXN')
            
            logger.info(f"👤 Usuario: {usuario}")
            logger.info("🔒 Password: [PROTEGIDO]")
            
            # MÉTODO 1: Selectores específicos mejorados (del código que funcionó)
            logger.info("🔍 Método 1: Buscando campos con selectores específicos...")
            
            campo_usuario = None
            campo_password = None
            
            # Intentar múltiples selectores para usuario (del código que funcionó)
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
                    campos = self.driver.find_elements(By.CSS_SELECTOR, selector)
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
                campo_password = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
                )
                logger.info("✅ Campo password encontrado")
            except:
                logger.error("❌ No se encontró campo password")
                return False
            
            # MÉTODO 2: Si no encontró usuario, usar posición (del código que funcionó)
            if not campo_usuario:
                logger.info("🔍 Método 2: Buscando por posición...")
                try:
                    inputs_visibles = []
                    todos_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    
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
            
            # LLENAR CAMPOS CON MÉTODO MEJORADO (del código que funcionó)
            logger.info("✏️ Llenando campos con método mejorado...")
            
            # Scroll y focus en usuario
            self.driver.execute_script("arguments[0].scrollIntoView(true);", campo_usuario)
            time.sleep(2)
            self.driver.execute_script("arguments[0].focus();", campo_usuario)
            time.sleep(1)
            
            # Limpiar y llenar usuario
            campo_usuario.clear()
            time.sleep(1)
            campo_usuario.send_keys(usuario)
            logger.info("✅ Usuario ingresado")
            time.sleep(2)
            
            # Focus en password
            self.driver.execute_script("arguments[0].focus();", campo_password)
            time.sleep(1)
            
            # Limpiar y llenar password
            campo_password.clear()
            time.sleep(1)
            campo_password.send_keys(password)
            logger.info("✅ Password ingresado")
            time.sleep(2)
            
            # Screenshot antes de submit
            self.driver.save_screenshot('salvum_antes_submit.png')
            logger.info("📸 Screenshot antes de submit")
            
            # BUSCAR Y HACER CLICK EN BOTÓN (del código que funcionó)
            logger.info("🔘 Buscando botón de submit...")
            
            boton_submit = None
            
            # Método 1: Por tipo submit
            try:
                boton_submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                logger.info("✅ Botón submit encontrado por tipo")
            except:
                pass
            
            # Método 2: Por texto
            if not boton_submit:
                try:
                    boton_submit = self.driver.find_element(By.XPATH, "//button[contains(text(), 'INGRESAR') or contains(text(), 'Ingresar') or contains(text(), 'LOGIN')]")
                    logger.info("✅ Botón submit encontrado por texto")
                except:
                    pass
            
            # Método 3: Primer botón disponible
            if not boton_submit:
                try:
                    botones = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in botones:
                        if btn.is_displayed() and btn.is_enabled():
                            boton_submit = btn
                            logger.info("✅ Usando primer botón disponible")
                            break
                except:
                    pass
            
            # EJECUTAR SUBMIT (del código que funcionó)
            if boton_submit:
                try:
                    # Scroll al botón
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", boton_submit)
                    time.sleep(2)
                    
                    # Click con JavaScript como backup
                    try:
                        boton_submit.click()
                        logger.info("🔘 Click normal ejecutado")
                    except:
                        self.driver.execute_script("arguments[0].click();", boton_submit)
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
            
            # ESPERAR RESPUESTA (del código que funcionó)
            logger.info("⏳ Esperando respuesta del servidor...")
            time.sleep(12)  # Espera más larga como en el código que funcionó
            
            # Screenshot después de submit
            self.driver.save_screenshot('salvum_despues_submit.png')
            logger.info("📸 Screenshot después de submit")
            
            # VERIFICAR RESULTADO (del código que funcionó)
            nueva_url = self.driver.current_url
            nuevo_titulo = self.driver.title
            
            logger.info(f"📍 Nueva URL: {nueva_url}")
            logger.info(f"📄 Nuevo título: {nuevo_titulo}")
            
            # Verificar si hay mensajes de error
            try:
                page_text = self.driver.page_source.lower()
                if "incorrecto" in page_text or "error" in page_text:
                    logger.warning("⚠️ Posible mensaje de error detectado")
            except:
                pass
            
            # Determinar éxito del login (del código que funcionó)
            if nueva_url != "https://prescriptores.salvum.cl/login" and "login" not in nueva_url.lower():
                logger.info("🎉 ¡LOGIN EXITOSO! - URL cambió")
                
                # Buscar indicadores de login exitoso
                try:
                    elementos_post_login = self.driver.find_elements(By.CSS_SELECTOR, 
                        "nav, .menu, .dashboard, .logout, .profile, [class*='menu'], [class*='nav']")
                    if elementos_post_login:
                        logger.info(f"✅ {len(elementos_post_login)} elementos post-login encontrados")
                except:
                    pass
                    
                return True
            else:
                logger.info("❌ Login falló - permanece en página de login")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error en proceso de login: {e}")
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
            nueva_solicitud_btn.click()
            time.sleep(5)
            
            # PASO 2: Datos del Cliente
            logger.info("📋 Llenando datos del cliente...")
            
            # RUT
            campo_rut = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "input[name*='rut'], input[id*='rut'], input[placeholder*='RUT']"
                ))
            )
            campo_rut.clear()
            campo_rut.send_keys(str(cliente_data['RUT']))
            time.sleep(2)
            
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
            btn_simular.click()
            time.sleep(8)
            
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
            btn_enviar.click()
            time.sleep(10)
            
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
        """Llenar campo si existe"""
        try:
            campo = self.driver.find_element(By.CSS_SELECTOR, selector)
            campo.clear()
            campo.send_keys(valor)
            time.sleep(2)
        except:
            pass
    
    def _click_continuar(self):
        """Click en botón continuar"""
        btn_continuar = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Continuar')]")
        btn_continuar.click()
        time.sleep(5)
    
    def _seleccionar_producto(self, producto):
        """Seleccionar producto"""
        try:
            campo_producto = self.driver.find_element(By.XPATH, "//select | //input[name*='producto']")
            if campo_producto.tag_name == 'select':
                select = Select(campo_producto)
                select.select_by_visible_text(producto)
            else:
                campo_producto.clear()
                campo_producto.send_keys(producto)
            time.sleep(2)
        except:
            pass
    
    def _configurar_cuotas_y_dia(self):
        """Configurar cuotas y día de vencimiento"""
        try:
            # Cuotas: 60
            campo_cuotas = self.driver.find_element(By.CSS_SELECTOR, "input[name*='cuota'], select[name*='cuota']")
            if campo_cuotas.tag_name == 'select':
                select = Select(campo_cuotas)
                select.select_by_value("60")
            else:
                campo_cuotas.clear()
                campo_cuotas.send_keys("60")
            time.sleep(2)
        except:
            pass
        
        try:
            # Día vencimiento: 2
            campo_dia = self.driver.find_element(By.CSS_SELECTOR, "input[name*='dia'], select[name*='dia']")
            if campo_dia.tag_name == 'select':
                select = Select(campo_dia)
                select.select_by_value("2")
            else:
                campo_dia.clear()
                campo_dia.send_keys("2")
            time.sleep(2)
        except:
            pass
    
    def _llenar_informacion_personal(self, cliente_data):
        """Llenar información personal fija"""
        # CI
        self._llenar_campo_si_existe("input[name*='ci'], input[name*='cedula']", "123456789")
        
        # Estado Civil: Soltero
        try:
            estado_civil = self.driver.find_element(By.CSS_SELECTOR, "select[name*='estado'], select[name*='civil']")
            select = Select(estado_civil)
            select.select_by_visible_text("Soltero")
            time.sleep(2)
        except:
            pass
        
        # Ubicación: Coquimbo, Elqui, La Serena
        self._seleccionar_ubicacion()
        
        # Dirección
        self._llenar_campo_si_existe("input[name*='direccion']", "Aven")
        
        # Modalidad trabajo: Jubilado
        try:
            modalidad = self.driver.find_element(By.CSS_SELECTOR, "select[name*='trabajo']")
            select = Select(modalidad)
            select.select_by_visible_text("Jubilado")
            time.sleep(2)
        except:
            pass
        
        # Renta líquida (desde planilla)
        renta_liquida = int(cliente_data['RENTA LIQUIDA'])
        self._llenar_campo_si_existe("input[name*='pension'], input[name*='renta'], input[name*='liquida']", str(renta_liquida))
        
        self._click_continuar()
    
    def _seleccionar_ubicacion(self):
        """Seleccionar ubicación fija"""
        try:
            region = self.driver.find_element(By.CSS_SELECTOR, "select[name*='region']")
            select = Select(region)
            select.select_by_visible_text("Coquimbo")
            time.sleep(2)
        except:
            pass
        
        try:
            ciudad = self.driver.find_element(By.CSS_SELECTOR, "select[name*='ciudad']")
            select = Select(ciudad)
            select.select_by_visible_text("Elqui")
            time.sleep(2)
        except:
            pass
        
        try:
            comuna = self.driver.find_element(By.CSS_SELECTOR, "select[name*='comuna']")
            select = Select(comuna)
            select.select_by_visible_text("La Serena")
            time.sleep(2)
        except:
            pass
    
    def procesar_todos_los_clientes(self):
        """Procesar todos los clientes de todas las planillas"""
        logger.info("🚀 Iniciando procesamiento masivo de múltiples planillas...")
        
        # Obtener todos los clientes
        todos_los_clientes = self.leer_todos_los_clientes()
        
        if not todos_los_clientes:
            logger.info("ℹ️ No hay clientes para procesar en ninguna planilla")
            return True
        
        total_clientes = len(todos_los_clientes)
        logger.info(f"📊 Total clientes a procesar: {total_clientes}")
        
        # Procesar cada cliente
        for idx, cliente in enumerate(todos_los_clientes, 1):
            logger.info(f"\n{'='*20} CLIENTE {idx}/{total_clientes} {'='*20}")
            logger.info(f"👥 Agente: {cliente['agente']}")
            logger.info(f"👤 Cliente: {cliente['Nombre Cliente']} - {cliente['RUT']}")
            
            try:
                # Procesar cliente
                if self.procesar_cliente_individual(cliente):
                    logger.info(f"✅ Cliente {idx} completado")
                else:
                    logger.error(f"❌ Cliente {idx} falló")
                
                # Pausa entre clientes
                if idx < total_clientes:
                    logger.info("⏳ Pausa antes del siguiente cliente...")
                    time.sleep(5)
                    
                    # Volver al dashboard
                    try:
                        self.driver.get("https://prescriptores.salvum.cl/")
                        time.sleep(3)
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"❌ Error procesando cliente {idx}: {e}")
                continue
        
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
        with open('reporte_multiple_planillas.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        # Mostrar reporte en consola
        logger.info("="*70)
        logger.info("📊 REPORTE FINAL - MÚLTIPLES PLANILLAS")
        logger.info("="*70)
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
        """Ejecutar automatización completa para múltiples planillas"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN MÚLTIPLES PLANILLAS SALVUM")
        logger.info("="*70)
        
        try:
            # 1. Cargar configuración de agentes
            if not self.cargar_configuracion_agentes():
                return False
            
            # 2. Configurar Google Sheets
            if not self.configurar_google_sheets():
                return False
            
            # 3. Verificar que hay clientes para procesar
            todos_los_clientes = self.leer_todos_los_clientes()
            if not todos_los_clientes:
                logger.info("ℹ️ No hay clientes para procesar")
                return True
            
            # 4. Configurar navegador
            self.configurar_navegador()
            
            # 5. Login
            if not self.realizar_login():
                return False
            
            # 6. Procesar todos los clientes
            self.procesar_todos_los_clientes()
            
            # 7. Generar reporte
            self.generar_reporte_final()
            
            logger.info("🎉 ¡AUTOMATIZACIÓN DE MÚLTIPLES PLANILLAS COMPLETADA!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en automatización: {e}")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Función principal"""
    automator = SalvumMultiplePlanillas()
    
    print("🏠 AUTOMATIZACIÓN SALVUM - MÚLTIPLES PLANILLAS")
    print("📊 Procesa clientes de múltiples agentes automáticamente")
    print("-"*70)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Ver reporte_multiple_planillas.json para detalles")
        print("📊 Estados actualizados en todas las planillas")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
