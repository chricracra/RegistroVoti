from app import app, db
from models import User, Subject, Grade

def initialize_database():
    with app.app_context():
        try:
            # Disabilita i vincoli per evitare errori durante la creazione
            db.session.execute('SET session_replication_role = replica;')
            
            # Crea tutte le tabelle
            db.create_all()
            
            # Riabilita i vincoli
            db.session.execute('SET session_replication_role = DEFAULT;')
            
            print("Tabelle create con successo!")
            return True
        except Exception as e:
            print(f"Errore nella creazione delle tabelle: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

# Esegui l'inizializzazione all'avvio
if os.environ.get('RUN_DB_INIT', 'true').lower() == 'true':
    if not initialize_database():
        print("Fallimento critico nell'inizializzazione del database")
