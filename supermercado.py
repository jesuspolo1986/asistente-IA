import db_manager
import ai_analyzer

def _orchestrate_analysis(conn, question, is_api_call=False):
    log_messages = [f"⚙️ Analizando: {question}"]
    
    # 1. Generar SQL
    sql_query, sql_error = ai_analyzer.generate_sql_query(question)
    
    if sql_error:
        final_response = f"Error de IA: {sql_error}"
    else:
        log_messages.append(f"SQL: {sql_query}")
        
        # 2. Ejecutar en DB
        columns, rows, db_error = db_manager.execute_dynamic_query(conn, sql_query)
        
        if db_error:
            final_response = f"Error de base de datos: {db_error}"
        else:
            # 3. Interpretar
            final_response = ai_analyzer.generate_ai_response(question, columns, rows, sql_query, None)

    if is_api_call:
        return final_response, log_messages
    else:
        print(f"\n{final_response}")

def run_chat_analysis_api(conn, question):
    response_text, _ = _orchestrate_analysis(conn, question, is_api_call=True)
    return response_text

def main_console():
    conn = db_manager.main_db_setup()
    if conn:
        print("Sistema listo. Haz tu pregunta.")
        while True:
            q = input("> ")
            if q.lower() in ('salir', 'exit'): break
            _orchestrate_analysis(conn, q)