import os
from app import app, db
from models import User, Subject, Grade

def reset_database():
    with app.app_context():
        # Disabilita i vincoli di chiave esterna
        db.session.execute('DROP TABLE IF EXISTS grades CASCADE')
        db.session.execute('DROP TABLE IF EXISTS subjects CASCADE')
        db.session.execute('DROP TABLE IF EXISTS users CASCADE')
        
        # Ricrea le tabelle
        db.create_all()
        
        print("Database resettato con successo!")

if __name__ == '__main__':
    reset_database()
