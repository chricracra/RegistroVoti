from app import app, db
from models import User, Subject, Grade

def initialize_database():
    with app.app_context():
        print("Creazione tabelle...")
        db.drop_all()  # Attenzione: cancella tutti i dati esistenti!
        db.create_all()
        
        # Verifica le tabelle
        inspector = inspect(db.engine)
        print("Tabelle esistenti:", inspector.get_table_names())
        
        print("Database inizializzato con successo!")

if __name__ == '__main__':
    initialize_database()
