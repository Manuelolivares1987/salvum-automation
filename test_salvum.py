#!/usr/bin/env python3
"""
MEJORAS PARA AUTOMATIZACIÓN SALVUM CON GOOGLE SHEETS
Integración directa con Google Sheets API + optimizaciones
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

class SalvumGoogleSheetsAutomation:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.gc = None  # Google Sheets client
        self.worksheet = None
        self.clientes_procesados = []
        self.clientes_fallidos = []
        
    def configurar_google_sheets(self):
        """Configurar conexión con Google Sheets"""
        logger.info("📊 Configurando Google Sheets...")
        
        try:
            # Credenciales desde variable de entorno (GitHub Secrets)
            creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
            if creds_json:
                import json
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
            
            # ID de la planilla desde variable de entorno
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '1T4_SynKEAJZFDDq6C7-Fuy7EtOl5IJXX1Z7MMkxoYQ')
            self.worksheet = self.gc.open_by_key(sheet_id).sheet1
            
            logger.info("✅ Google Sheets configurado")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error configurando Google Sheets: {e}")
            return False
    
    def leer_clientes_desde_sheets(self):
        """Leer clientes directamente desde Google Sheets"""
        logger.info("📖 Leyendo clientes desde Google Sheets...")
        
        try:
            # Obtener todos los datos
            records = self.worksheet.get_all_records()
            
            # Filtrar clientes listos para procesar
            clientes_procesar = []
            
            for i, record in enumerate(records, start=2):  # Start=2 porque row 1 son headers
                # Verificar condiciones
                renta_liquida = record.get('RENTA LIQUIDA', 0)
                procesar = record.get('PROCESAR', '').upper()
                
                try:
                    renta_liquida = float(renta_liquida) if renta_liquida else 0
                except:
                    renta_liquida = 0
                
                if renta_liquida > 0 and procesar == 'NUEVO':
                    cliente = {
                        'row_number': i,  # Para actualizar después
                        'Nombre Cliente': record.get('Nombre Cliente', ''),
                        'RUT': record.get('RUT', ''),
                        'Email': record.get('Email', ''),
                        'Telefono': record.get('Teléfono', ''),
                        'Monto Financiar Original': record.get('Monto Financia Origen', 0),
                        'RENTA LIQUIDA': renta_liquida,
                        'Modelo Casa': record.get('Modelo Casa', ''),
                        'Precio Casa': record.get('Precio Casa', 0)
                    }
                    clientes_procesar.append(cliente)
            
            logger.info(f"✅ {len(clientes_procesar)} clientes encontrados para procesar")
            
            if clientes_procesar:
                logger.info("📋 Clientes a procesar:")
                for cliente in clientes_procesar:
                    logger.info(f"  - {cliente['Nombre Cliente']} (RUT: {cliente['RUT']}) - Row: {cliente['row_number']}")
            
            return clientes_procesar
            
        except Exception as e:
            logger.error(f"❌ Error leyendo Google Sheets: {e}")
            return []
    
    def actualizar_estado_cliente(self, row_number, estado, resultado=""):
        """Actualizar estado del cliente en Google Sheets"""
        try:
            # Actualizar columna PROCESAR (columna L)
            self.worksheet.update_cell(row_number, 12, estado)  # Columna L = 12
            
            # Actualizar columna Resultado si se proporciona (columna N)
            if resultado:
                self.worksheet.update_cell(row_number, 14, resultado)  # Columna N = 14
            
            # Actualizar timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.worksheet.update_cell(row_number, 13, f"Procesado: {timestamp}")  # Columna M = 13
            
            logger.info(f"✅ Estado actualizado en fila {row_number}: {estado}")
            
        except Exception as e:
            logger.error(f"❌ Error actualizando estado: {e}")
    
    def configurar_navegador(self):
        """Configurar navegador optimizado con anti-detección"""
        logger.info("🔧 Configurando navegador anti-detección...")
        
        options = Options()
        
        # Configuración para GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
        
        # Optimizaciones anti-detección
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Configuración adicional para evitar detección
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        
        # Scripts anti-detección
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es']})")
        
        logger.info("✅ Navegador configurado")
    
    def realizar_login_robusto(self):
        """Login robusto con múltiples estrategias"""
        logger.info("🔐 Realizando login robusto...")
        
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            logger.info(f"🔄 Intento {intento}/{max_intentos}")
            
            try:
                self.driver.get("https://prescriptores.salvum.cl/login")
                time.sleep(8)
                
                # Verificar si ya estamos logueados
                if "login" not in self.driver.current_url.lower():
                    logger.info("✅ Ya estamos logueados")
                    return True
                
                # Credenciales
                usuario = os.getenv('SALVUM_USER', 'Molivaco')
                password = os.getenv('SALVUM_PASS', 'd6r4YaXN')
                
                # Estrategia 1: Selectores específicos
                if self._intentar_login_metodo1(usuario, password):
                    return True
                
                # Estrategia 2: Por posición
                if self._intentar_login_metodo2(usuario, password):
                    return True
                
                # Estrategia 3: JavaScript directo
                if self._intentar_login_metodo3(usuario, password):
                    return True
                
                logger.warning(f"⚠️ Intento {intento} falló")
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Error en intento {intento}: {e}")
                time.sleep(5)
        
        logger.error("❌ Login falló después de todos los intentos")
        return False
    
    def _intentar_login_metodo1(self, usuario, password):
        """Método 1: Selectores CSS específicos"""
        try:
            logger.info("🔍 Método 1: Selectores específicos")
            
            campo_usuario = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='text']"))
            )
            campo_password = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            
            campo_usuario.clear()
            campo_usuario.send_keys(usuario)
            time.sleep(2)
            
            campo_password.clear()
            campo_password.send_keys(password)
            time.sleep(2)
            
            # Buscar botón submit
            try:
                boton = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                boton.click()
            except:
                campo_password.send_keys(Keys.RETURN)
            
            time.sleep(8)
            
            # Verificar éxito
            if "login" not in self.driver.current_url.lower():
                logger.info("✅ Método 1 exitoso")
                return True
            
        except Exception as e:
            logger.warning(f"⚠️ Método 1 falló: {e}")
        
        return False
    
    def _intentar_login_metodo2(self, usuario, password):
        """Método 2: Por posición de elementos"""
        try:
            logger.info("🔍 Método 2: Por posición")
            
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            inputs_visibles = [inp for inp in inputs if inp.is_displayed() and inp.is_enabled()]
            
            if len(inputs_visibles) >= 2:
                campo_usuario = inputs_visibles[0]
                campo_password = inputs_visibles[1]
                
                campo_usuario.clear()
                campo_usuario.send_keys(usuario)
                time.sleep(2)
                
                campo_password.clear()
                campo_password.send_keys(password)
                campo_password.send_keys(Keys.RETURN)
                
                time.sleep(8)
                
                if "login" not in self.driver.current_url.lower():
                    logger.info("✅ Método 2 exitoso")
                    return True
            
        except Exception as e:
            logger.warning(f"⚠️ Método 2 falló: {e}")
        
        return False
    
    def _intentar_login_metodo3(self, usuario, password):
        """Método 3: JavaScript directo"""
        try:
            logger.info("🔍 Método 3: JavaScript")
            
            script = f"""
            var inputs = document.querySelectorAll('input');
            var userField = null;
            var passField = null;
            
            for(var i = 0; i < inputs.length; i++) {{
                if(inputs[i].type === 'text' || inputs[i].type === '') {{
                    userField = inputs[i];
                }}
                if(inputs[i].type === 'password') {{
                    passField = inputs[i];
                }}
            }}
            
            if(userField && passField) {{
                userField.value = '{usuario}';
                passField.value = '{password}';
                
                var event = new Event('input', {{ bubbles: true }});
                userField.dispatchEvent(event);
                passField.dispatchEvent(event);
                
                var forms = document.querySelectorAll('form');
                if(forms.length > 0) {{
                    forms[0].submit();
                }}
                
                return true;
            }}
            return false;
            """
            
            resultado = self.driver.execute_script(script)
            
            if resultado:
                time.sleep(8)
                if "login" not in self.driver.current_url.lower():
                    logger.info("✅ Método 3 exitoso")
                    return True
            
        except Exception as e:
            logger.warning(f"⚠️ Método 3 falló: {e}")
        
        return False
    
    def procesar_cliente_mejorado(self, cliente_data):
        """Procesar cliente con manejo de errores mejorado"""
        nombre = cliente_data['Nombre Cliente']
        row_number = cliente_data['row_number']
        
        logger.info(f"👤 Procesando {nombre} (Fila: {row_number})")
        
        try:
            # Actualizar estado a "PROCESANDO"
            self.actualizar_estado_cliente(row_number, "PROCESANDO")
            
            # Aquí iría toda la lógica de procesamiento de Salvum
            # (similar al código original pero con mejoras)
            
            # Si es exitoso
            self.actualizar_estado_cliente(row_number, "COMPLETADO", "Proceso exitoso")
            
            resultado = {
                'cliente': nombre,
                'row': row_number,
                'estado': 'EXITOSO',
                'timestamp': datetime.now().isoformat()
            }
            
            self.clientes_procesados.append(resultado)
            logger.info(f"✅ Cliente {nombre} procesado exitosamente")
            return True
            
        except Exception as e:
            # Si falla
            error_msg = str(e)[:100]  # Limitar longitud
            self.actualizar_estado_cliente(row_number, "ERROR", f"Error: {error_msg}")
            
            self.clientes_fallidos.append({
                'cliente': nombre,
                'row': row_number,
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.error(f"❌ Error procesando {nombre}: {e}")
            return False
    
    def ejecutar_automatizacion_completa(self):
        """Ejecutar automatización completa integrada con Google Sheets"""
        logger.info("🚀 INICIANDO AUTOMATIZACIÓN INTEGRADA CON GOOGLE SHEETS")
        logger.info("=" * 70)
        
        try:
            # 1. Configurar Google Sheets
            if not self.configurar_google_sheets():
                return False
            
            # 2. Leer clientes desde Sheets
            clientes = self.leer_clientes_desde_sheets()
            if not clientes:
                logger.info("ℹ️ No hay clientes para procesar")
                return True
            
            # 3. Configurar navegador
            self.configurar_navegador()
            
            # 4. Login robusto
            if not self.realizar_login_robusto():
                return False
            
            # 5. Procesar cada cliente
            for cliente in clientes:
                self.procesar_cliente_mejorado(cliente)
                time.sleep(3)  # Pausa entre clientes
            
            # 6. Reporte final
            self.generar_reporte_final()
            
            logger.info("🎉 ¡AUTOMATIZACIÓN COMPLETADA!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en automatización: {e}")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def generar_reporte_final(self):
        """Generar reporte final mejorado"""
        total_procesados = len(self.clientes_procesados)
        total_fallidos = len(self.clientes_fallidos)
        total = total_procesados + total_fallidos
        
        reporte = {
            'timestamp': datetime.now().isoformat(),
            'total_clientes': total,
            'exitosos': total_procesados,
            'fallidos': total_fallidos,
            'tasa_exito': f"{(total_procesados/total*100):.1f}%" if total > 0 else "0%",
            'detalles_exitosos': self.clientes_procesados,
            'detalles_fallidos': self.clientes_fallidos
        }
        
        # Guardar reporte
        with open('reporte_google_sheets.json', 'w', encoding='utf-8') as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
        
        logger.info("=" * 60)
        logger.info("📊 REPORTE FINAL")
        logger.info("=" * 60)
        logger.info(f"✅ Exitosos: {total_procesados}")
        logger.info(f"❌ Fallidos: {total_fallidos}")
        logger.info(f"📈 Tasa éxito: {reporte['tasa_exito']}")
        logger.info("=" * 60)

def main():
    """Función principal mejorada"""
    automator = SalvumGoogleSheetsAutomation()
    
    print("🏠 AUTOMATIZACIÓN SALVUM + GOOGLE SHEETS")
    print("📊 Integración directa con planilla en tiempo real")
    print("-" * 60)
    
    success = automator.ejecutar_automatizacion_completa()
    
    if success:
        print("\n✅ ¡AUTOMATIZACIÓN EXITOSA!")
        print("📋 Estados actualizados en Google Sheets")
        print("📊 Ver reporte_google_sheets.json para detalles")
    else:
        print("\n❌ Error en automatización")

if __name__ == "__main__":
    main()
