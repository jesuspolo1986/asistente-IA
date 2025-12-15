# supermercado.py (VERSIÓN FINAL Y COMPLETA - Consola y API Ready)

import db_manager
import ai_analyzer
import os # Necesario para la conexión a la DB

# --- Lógica del Orquestador (Text-to-SQL con Autocorrección) ---

def _orchestrate_analysis(conn, question, is_api_call=False):
    """
    Función interna que maneja la lógica central de Text-to-SQL y Autocorrección.
    Retorna el texto de respuesta (para API) o imprime (para consola).
    """
    max_attempts = 2
    db_error = None 
    final_response = None
    
    # Inicio de los logs
    log_messages = [f"\n⚙️  Iniciando análisis para: {question}"]

    for attempt in range(1, max_attempts + 1):
        log_messages.append(f"\n--- Intento {attempt}/{max_attempts} ---")
        
        # 1. Preparar contexto de corrección
        correction_context = f"El intento anterior de SQL falló. Por favor, revisa el esquema y genera una consulta SQL corregida. El error anterior fue: {db_error}" if attempt > 1 and db_error else None

        log_messages.append(f"⚙️  [1/3] Solicitando SQL a Gemini...")
        
        # 2. Generar SQL
        sql_query, sql_error = ai_analyzer.generate_sql_query(question, correction_context)
        
        if sql_error:
            # Error en la generación de IA
            final_response = f"ERROR: Falló al generar SQL. Detalle: {sql_error}"
            break
            
        log_messages.append(f"   [SQL Generado] {sql_query}")
        
        # 3. Ejecutar SQL
        log_messages.append(f"⚙️  [2/3] Ejecutando consulta en la Base de Datos...")
        
        columns, rows, db_error = db_manager.execute_dynamic_query(conn, sql_query)
        
        if db_error:
            # Error de la DB, intentar corregir en el próximo bucle
            log_messages.append(f"   [DB ERROR] La consulta falló: {db_error}")
            continue # Vuelve al inicio del bucle para el intento 2
        
        # 4. Interpretar Resultados (Ejecución Exitosa)
        log_messages.append(f"⚙️  [3/3] Interpretando resultados con Gemini...")
        
        ai_response = ai_analyzer.generate_ai_response(
            question=question,
            columns=columns,
            data=rows,
            sql_query=sql_query,
            db_error=None
        )
        
        final_response = ai_response
        break # Éxito: salimos del bucle de intentos
        
    # Si la respuesta final es None después del bucle, falló en ambos intentos.
    if final_response is None:
        final_response = f"\n🚨 ANÁLISIS FALLIDO: La consulta no pudo ser generada o corregida después de {max_attempts} intentos. Por favor, reformule su pregunta."

    # Gestión de la Salida
    if is_api_call:
        # Para la API, retornamos solo la respuesta final y el log de fondo
        return final_response, log_messages
    else:
        # Para la Consola, imprimimos los logs y la respuesta
        for msg in log_messages:
            print(msg)
        print("\n--- 🤖 RESPUESTA DEL ANALISTA CONVERSACIONAL ---")
        print(final_response)
        print("------------------------------------------")


# --- Funciones de Interfaz Pública ---

def run_chat_analysis(conn, question):
    """Interfaz de consola. Ejecuta el análisis e imprime los resultados."""
    _orchestrate_analysis(conn, question, is_api_call=False)


def run_chat_analysis_api(conn, question):
    """Interfaz para API Flask. Ejecuta el análisis y retorna la respuesta (texto)."""
    response_text, log_messages = _orchestrate_analysis(conn, question, is_api_call=True)
    
    # Opcional: imprimir logs de API en la terminal del servidor Flask
    for msg in log_messages:
        print(msg)
        
    return response_text


# --- Función Main (Modo Consola) ---

def main():
    """Función principal del chat en modo consola."""
    
    # Configuración inicial: llama UNA SOLA VEZ para crear/poblar/conectar
    conn = db_manager.main_db_setup()

    if conn is None:
        print("Error crítico: No se pudo conectar a la base de datos.")
        return

    print("\n" + "="*60)
    print("💬 ASISTENTE CONVERSACIONAL (v3.0 - Demo de Datos Masivos)")
    print("="*60)
    print("Base de datos poblada con 5,000 ventas. Escribe tu pregunta o 'salir'.")
    
    while True:
        question = input("\nTu pregunta: ").strip()
        
        if question.lower() in ('salir', 'exit'):
            print("¡Gracias por usar el Analista Conversacional! Adiós.")
            break
        elif not question:
            continue
        
        run_chat_analysis(conn, question) # Usa la función de consola

    conn.close()

if __name__ == '__main__':
    # Esta parte se ejecuta solo si corres python supermercado.py directamente
    main()