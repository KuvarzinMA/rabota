import psycopg2

# Параметры подключения
conn_params = {
    "host": "10.2.1.50",
    "database": "postgres",
    "user": "rpismo",
    "password": "22rpismo11"
}

try:
    # Подключаемся к базе
    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            # SQL-запрос для получения списка таблиц
            query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
            """
            cur.execute(query)

            tables = cur.fetchall()
            print("Список таблиц в базе:")
            for table in tables:
                print(f"- {table[0]}")

            cur.execute("SELECT * FROM users LIMIT 10;")  # LIMIT 10, чтобы не зависнуть, если таблица огромная
            rows = cur.fetchall()

            for row in rows:
                print(row)

except Exception as e:
    print(f"Ошибка при подключении: {e}")