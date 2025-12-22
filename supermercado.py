import db_manager
import ai_analyzer
import os

# --- Lógica del Orquestador (Text-to-SQL con Autocorrección) ---

def _orchestrate_analysis(conn, question, is_api_call=False):
    """
    Maneja la lógica central. 
    Nota: 'conn' ahora es una conexión de PostgreSQL.
    """
    max_attempts = 2
    db_error = None 
    final_response = None
    
    log_messages = [f"\n⚙️  Iniciando análisis cloud para: {question}"]

    for attempt in range(1, max_attempts + 1):
        log_messages.append(f"\n--- Intento {attempt}/{max_attempts} ---")
        
        # 1. Preparar contexto de corrección
        correction_context = f"El intento anterior de SQL falló en PostgreSQL. El error fue: {db_error}" if attempt > 1 and db_error else None

        log_messages.append(f"⚙️  [1/3] Generando SQL con Gemini...")
        
        # 2. Generar SQL
        sql_query, sql_error = ai_analyzer.generate_sql_query(question, correction_context)
        
        if sql_error:
            final_response = f"ERROR: IA falló al generar SQL. Detalle: {sql_error}"
            break
            
        log_messages.append(f"   [SQL] {sql_query}")
        
        # 3. Ejecutar SQL (Aquí es donde db_manager usa PostgreSQL)
        log_messages.append(f"⚙️  [2/3] Consultando base de datos en Render...")
        
        # IMPORTANTE: db_manager.execute_dynamic_query ya está listo para Postgres
        columns, rows, db_error = db_manager.execute_dynamic_query(sql_query) # Quitamos 'conn' si tu db_manager lo maneja internamente, o lo dejamos si lo requiere.
        
        if db_error:
            log_messages.append(f"   [DB ERROR] {db_error}")
            continue 
        
        # 4. Interpretar Resultados
        log_messages.append(f"⚙️  [3/3] Generando respuesta narrativa...")
        
        ai_response = ai_analyzer.generate_ai_response(
            question=question,
            columns=columns,
            data=rows,
            sql_query=sql_query,
            db_error=None
        )
        
        final_response = ai_response
        break 
        
    if final_response is None:
        final_response = f"\n🚨 ANÁLISIS FALLIDO en la nube tras {max_attempts} intentos."

    if is_api_call:
        return final_response, log_messages
    else:
        for msg in log_messages: print(msg)
        print(f"\n--- 🤖 ANALISTA ---\n{final_response}")

# --- Funciones de Interfaz Pública ---

def run_chat_analysis(conn, question):
    _orchestrate_analysis(conn, question, is_api_call=False)

def run_chat_analysis_api(conn, question):
    # Nota: Pasamos la conexión pero db_manager la gestionará de forma global/cloud
    response_text, log_messages = _orchestrate_analysis(conn, question, is_api_call=True)
    for msg in log_messages:
        print(msg)
    return response_text

# --- Modo Consola (Ajustado para Cloud) ---

def main():
    # En lugar de setup local, usamos la conexión cloud
    db_manager.create_tables() # Crea tablas en Render si no existen
    db_manager.seed_data()     # Puebla con los 5000 datos iniciales en la nube
    
    conn = db_manager.get_db_connection()

    if conn is None:
        print("Error: No hay conexión con la DB de Render.")
        return

    print("\n" + "="*60)
    print("💬 ASISTENTE PRO ANALYST - MODO CLOUD POSTGRESQL")
    print("="*60)
    
    while True:
        question = input("\nPregunta a la DB Cloud: ").strip()
        if question.lower() in ('salir', 'exit'): break
        if not question: continue
        run_chat_analysis(conn, question)

    conn.close()

if __name__ == '__main__':
    main()