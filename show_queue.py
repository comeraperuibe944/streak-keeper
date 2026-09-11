import sqlite3

conn = sqlite3.connect(os.environ.get("STREAK_DB_PATH", os.path.join(os.path.dirname(__file__), "streak.db")))
c = conn.cursor()

print(f"{'ID':<4} | {'Tipo':<12} | {'Repo':<35} | {'Agendamento (BRT)':<26} | {'Status':<10}")
print("-" * 95)
for r in c.execute('SELECT id, file_path, repo, scheduled_at, status FROM queue ORDER BY id ASC'):
    tipo = 'Repositorio' if r[1] == '__create_repo__' else 'Commit'
    sched = r[3] or 'Nao agendado'
    print(f"#{r[0]:<3} | {tipo:<12} | {r[2]:<35} | {sched:<26} | {r[4]:<10}")
conn.close()
