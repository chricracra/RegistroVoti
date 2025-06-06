import os
import json
import re
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import inspect, text

app = Flask(__name__)

# Configurazione iniziale
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')

# Funzione per correggere la connection string
def create_db_uri():
    db_url = os.environ.get('DATABASE_URL', '')
    
    if not db_url:
        # Modalità sviluppo locale con SQLite
        basedir = os.path.abspath(os.path.dirname(__file__))
        instance_path = os.path.join(basedir, 'instance')
        os.makedirs(instance_path, exist_ok=True)
        return f'sqlite:///{os.path.join(instance_path, "site.db")}'
    
    # Correzione per Render + Neon
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url

# Configurazione database
app.config['SQLALCHEMY_DATABASE_URI'] = create_db_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 10,
    'max_overflow': 20
}
app.permanent_session_lifetime = timedelta(days=30)

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    theme = db.Column(db.String(10), default='light')  # Aggiungi questo campo


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)

class Grade(db.Model):
    __tablename__ = 'grades'
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False, default=1.0)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    subject_id = db.Column(db.Integer, nullable=False)

# Funzione per verificare e creare le tabelle
def initialize_database():
    with app.app_context():
        try:
            # Verifica se le tabelle esistono già
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            required_tables = {'users', 'subjects', 'grades'}
            
            # Crea le tabelle mancanti
            for table in required_tables:
                if table not in existing_tables:
                    print(f"Creazione tabella: {table}")
                    
                    if table == 'users':
                        db.session.execute(text("""
                            CREATE TABLE users (
                                id SERIAL PRIMARY KEY,
                                username VARCHAR(80) UNIQUE NOT NULL,
                                password VARCHAR(120) NOT NULL
                            )
                        """))
                    elif table == 'subjects':
                        db.session.execute(text("""
                            CREATE TABLE subjects (
                                id SERIAL PRIMARY KEY,
                                name VARCHAR(100) NOT NULL,
                                user_id INTEGER NOT NULL
                            )
                        """))
                    elif table == 'grades':
                        db.session.execute(text("""
                            CREATE TABLE grades (
                                id SERIAL PRIMARY KEY,
                                value FLOAT NOT NULL,
                                weight FLOAT NOT NULL DEFAULT 1.0,
                                date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                subject_id INTEGER NOT NULL
                            )
                        """))
                    
                    db.session.commit()
                    print(f"Tabella {table} creata con successo")
            
            # Verifica se la colonna theme esiste nella tabella users
            if 'users' in existing_tables:
                columns = [col['name'] for col in inspector.get_columns('users')]
                if 'theme' not in columns:
                    print("Aggiunta colonna 'theme' alla tabella users")
                    try:
                        db.session.execute(text("ALTER TABLE users ADD COLUMN theme VARCHAR(10) DEFAULT 'light'"))
                        db.session.commit()
                    except Exception as e:
                        print(f"Errore aggiunta colonna theme: {str(e)}")
            
            print("Verifica database completata")
            return True
        except Exception as e:
            print(f"Errore inizializzazione DB: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

# Esegui l'inizializzazione all'avvio
initialize_database()

# Funzioni di calcolo
def calculate_weighted_average(grades):
    if not grades:
        return 0
    weighted_sum = sum(grade.value * grade.weight for grade in grades)
    total_weight = sum(grade.weight for grade in grades)
    return round(weighted_sum / total_weight, 2) if total_weight else 0

def calculate_overall_average(user_id):
    # Calcola la media generale di tutti i voti di un utente
    try:
        # Query per ottenere tutti i voti dell'utente
        grades = db.session.execute(text("""
            SELECT g.value, g.weight
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            WHERE s.user_id = :user_id
        """), {'user_id': user_id}).fetchall()
        
        if not grades:
            return 0
        
        weighted_sum = sum(grade.value * grade.weight for grade in grades)
        total_weight = sum(grade.weight for grade in grades)
        return round(weighted_sum / total_weight, 2) if total_weight else 0
    except Exception as e:
        print(f"Errore calcolo media: {str(e)}")
        return 0

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            # Verifica se l'utente esiste già
            existing_user = db.session.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {'username': username}
            ).fetchone()
            
            if existing_user:
                flash('Username già esistente!', 'error')
                return redirect(url_for('register'))
            
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            
            # Crea nuovo utente con tema predefinito
            db.session.execute(
                text("INSERT INTO users (username, password, theme) VALUES (:username, :password, 'light')"),  # Modifica questa query
                {'username': username, 'password': hashed_password}
            )
            db.session.commit()
            
            flash('Registrazione completata! Effettua il login.', 'success')
            return redirect(url_for('login'))
        
        except Exception as e:
            flash(f'Errore durante la registrazione: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            user = db.session.execute(
                text("SELECT * FROM users WHERE username = :username"),
                {'username': username}
            ).fetchone()
            
            if user and check_password_hash(user.password, password):
                session.permanent = True
                session['user_id'] = user.id
                session['username'] = user.username
                session['theme'] = user.theme  # Aggiungi questa linea
                return redirect(url_for('dashboard'))
            else:
                flash('Credenziali non valide!', 'error')
        
        except Exception as e:
            flash(f'Errore durante il login: {str(e)}', 'error')
    
    return render_template('login.html')


@app.route('/change_theme', methods=['POST'])
def change_theme():
    if 'user_id' not in session:
        return jsonify({'success': False})
    
    theme = request.json.get('theme')
    if theme not in ['light', 'dark']:
        return jsonify({'success': False})
    
    try:
        # Aggiorna il tema nel database
        db.session.execute(
            text("UPDATE users SET theme = :theme WHERE id = :user_id"),
            {'theme': theme, 'user_id': session['user_id']}
        )
        db.session.commit()
        
        # Aggiorna la sessione
        session['theme'] = theme
        return jsonify({'success': True})
    except Exception as e:
        print(f"Errore cambio tema: {str(e)}")
        return jsonify({'success': False})



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    try:
        # Recupera tutte le materie dell'utente
        subjects = db.session.execute(
            text("SELECT * FROM subjects WHERE user_id = :user_id"),
            {'user_id': user_id}
        ).fetchall()
        
        # Prepara i dati per il frontend
        subjects_data = []
        for subject in subjects:
            # Recupera i voti per questa materia
            grades = db.session.execute(
                text("SELECT * FROM grades WHERE subject_id = :subject_id"),
                {'subject_id': subject.id}
            ).fetchall()
            
            # Calcola la media della materia
            avg = calculate_weighted_average(grades) if grades else 0
            
            subjects_data.append({
                'id': subject.id,
                'name': subject.name,
                'average': avg,
                'grade_count': len(grades)  # Manteniamo solo il conteggio voti
            })
        
        # Calcola la media generale
        overall_avg = calculate_overall_average(user_id)
        
        # Prepara dati per il grafico radar
        radar_labels = [s.name for s in subjects]
        radar_data = [s['average'] for s in subjects_data]  # Usiamo direttamente la media
        
        return render_template('dashboard.html',
                               subjects=subjects_data,
                               overall_avg=overall_avg,
                               username=session['username'],
                               radar_labels=json.dumps(radar_labels),
                               radar_data=json.dumps(radar_data))
    
    except Exception as e:
        flash(f'Errore nel caricamento della dashboard: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/add_subject', methods=['POST'])
def add_subject():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    name = request.form['name']
    if name:
        try:
            # Aggiungi nuova materia
            db.session.execute(
                text("INSERT INTO subjects (name, user_id) VALUES (:name, :user_id)"),
                {'name': name, 'user_id': session['user_id']}
            )
            db.session.commit()
            flash('Materia aggiunta con successo!', 'success')
        except Exception as e:
            flash(f'Errore nell\'aggiunta della materia: {str(e)}', 'error')
            db.session.rollback()
    
    return redirect(url_for('dashboard'))

@app.route('/subject/<int:subject_id>')
def view_subject(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Recupera la materia
        subject = db.session.execute(
            text("SELECT * FROM subjects WHERE id = :id AND user_id = :user_id"),
            {'id': subject_id, 'user_id': session['user_id']}
        ).fetchone()
        
        if not subject:
            flash('Materia non trovata!', 'error')
            return redirect(url_for('dashboard'))
        
        # Recupera i voti della materia
        grades = db.session.execute(
            text("SELECT * FROM grades WHERE subject_id = :subject_id ORDER BY date"),
            {'subject_id': subject_id}
        ).fetchall()
        
        # Calcola la media
        average = calculate_weighted_average(grades)
        
        # Prepara dati per il grafico
        chart_dates = [g.date.strftime('%Y-%m-%d') for g in grades] if grades else []
        chart_values = [g.value for g in grades] if grades else []
        
        return render_template('subject.html',
                               subject=subject,
                               average=average,
                               grades=grades,
                               username=session['username'],
                               chart_dates=json.dumps(chart_dates),
                               chart_values=json.dumps(chart_values))
    
    except Exception as e:
        flash(f'Errore nel caricamento della materia: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/add_grade/<int:subject_id>', methods=['POST'])
def add_grade(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        value = float(request.form['value'])
        weight = float(request.form.get('weight', 1))
        
        # Verifica che la materia appartenga all'utente
        subject = db.session.execute(
            text("SELECT id FROM subjects WHERE id = :id AND user_id = :user_id"),
            {'id': subject_id, 'user_id': session['user_id']}
        ).fetchone()
        
        if not subject:
            flash('Materia non trovata!', 'error')
            return redirect(url_for('dashboard'))
        
        # Aggiungi nuovo voto
        db.session.execute(
            text("""
                INSERT INTO grades (value, weight, date, subject_id)
                VALUES (:value, :weight, CURRENT_TIMESTAMP, :subject_id)
            """),
            {
                'value': value,
                'weight': weight,
                'subject_id': subject_id
            }
        )
        db.session.commit()
        flash('Voto aggiunto con successo!', 'success')
    
    except ValueError:
        flash('Valore non valido!', 'error')
    except Exception as e:
        flash(f'Errore nell\'aggiunta del voto: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('view_subject', subject_id=subject_id))

@app.route('/delete_grade/<int:grade_id>', methods=['POST'])
def delete_grade(grade_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Verifica che il voto appartenga all'utente
        grade = db.session.execute(
            text("""
                SELECT g.id, g.subject_id
                FROM grades g
                JOIN subjects s ON g.subject_id = s.id
                WHERE g.id = :grade_id AND s.user_id = :user_id
            """),
            {'grade_id': grade_id, 'user_id': session['user_id']}
        ).fetchone()
        
        if not grade:
            flash('Voto non trovato!', 'error')
            return redirect(url_for('dashboard'))
        
        # Elimina il voto
        db.session.execute(
            text("DELETE FROM grades WHERE id = :id"),
            {'id': grade_id}
        )
        db.session.commit()
        flash('Voto eliminato con successo!', 'success')
        return redirect(url_for('view_subject', subject_id=grade.subject_id))
    
    except Exception as e:
        flash(f'Errore nell\'eliminazione del voto: {str(e)}', 'error')
        db.session.rollback()
        return redirect(url_for('dashboard'))

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Verifica che la materia appartenga all'utente
        subject = db.session.execute(
            text("SELECT id FROM subjects WHERE id = :id AND user_id = :user_id"),
            {'id': subject_id, 'user_id': session['user_id']}
        ).fetchone()
        
        if not subject:
            flash('Materia non trovata!', 'error')
            return redirect(url_for('dashboard'))
        
        # Elimina prima tutti i voti associati
        db.session.execute(
            text("DELETE FROM grades WHERE subject_id = :subject_id"),
            {'subject_id': subject_id}
        )
        
        # Elimina la materia
        db.session.execute(
            text("DELETE FROM subjects WHERE id = :id"),
            {'id': subject_id}
        )
        
        db.session.commit()
        flash('Materia eliminata con successo!', 'success')
    
    except Exception as e:
        flash(f'Errore nell\'eliminazione della materia: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('dashboard'))

# Avvio applicazione
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
