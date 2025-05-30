from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json  # Aggiungi questa linea
from sqlalchemy import inspect

app = Flask(__name__)

# Leggi la secret key dall'ambiente
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key')

if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    f'sqlite:///{os.path.join(instance_path, "site.db")}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 299,
    'pool_timeout': 20
}
app.permanent_session_lifetime = timedelta(days=30)

db = SQLAlchemy(app)

# 4. Modelli
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    subjects = db.relationship('Subject', backref='user', lazy=True)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    grades = db.relationship('Grade', backref='subject', lazy=True)
    
    def completion(self):
        if not self.grades:
            return 0
        return min(100, len(self.grades) * 10)  # 10% per ogni voto, max 100%

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False, default=1.0)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

# 5. Funzione per ottenere i nomi delle tabelle
def get_table_names(engine):
    inspector = inspect(engine)
    return inspector.get_table_names()

# 6. Creazione tabelle DENTRO un contesto applicativo
with app.app_context():
    # Controlla se il database esiste già
    db_file = os.path.join(basedir, 'site.db')
    db_exists = os.path.exists(db_file)
    
    # Crea tutte le tabelle
    db.create_all()
    print(f"Database initialized. Existed: {db_exists}")
    print("Tabelle create:", get_table_names(db.engine))

# 7. Funzioni di calcolo
def calculate_weighted_average(grades):
    if not grades:
        return 0
    weighted_sum = sum(grade.value * grade.weight for grade in grades)
    total_weight = sum(grade.weight for grade in grades)
    return round(weighted_sum / total_weight, 2)

def calculate_overall_average(user):
    subjects = Subject.query.filter_by(user_id=user.id).all()
    if not subjects:
        return 0
    
    weighted_averages = []
    weights = []
    
    for subject in subjects:
        if subject.grades:
            subject_avg = calculate_weighted_average(subject.grades)
            subject_weight = sum(grade.weight for grade in subject.grades)
            weighted_averages.append(subject_avg)
            weights.append(subject_weight)
    
    if not weighted_averages:
        return 0
    
    total = sum(avg * weight for avg, weight in zip(weighted_averages, weights))
    total_weight = sum(weights)
    return round(total / total_weight, 2)

# ... (il resto del codice delle routes rimane invariato) ...


# 7. Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username già esistente!', 'error')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registrazione completata! Effettua il login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        else:
            flash('Credenziali non valide!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    subjects = Subject.query.filter_by(user_id=user.id).all()
    
    # Calcola le medie per ogni materia
    subjects_data = []
    for subject in subjects:
        avg = calculate_weighted_average(subject.grades)
        subjects_data.append({
            'id': subject.id,
            'name': subject.name,
            'average': avg,
            'completion': subject.completion(),
            'grade_count': len(subject.grades)
        })
    
    # Calcola la media generale
    overall_avg = calculate_overall_average(user)
    
    # Prepara dati per il grafico a stella
    radar_labels = [s.name for s in subjects]
    radar_data = [s.completion() for s in subjects]
    
    return render_template('dashboard.html',
                           subjects=subjects_data,
                           overall_avg=overall_avg,
                           username=session['username'],
                           radar_labels=json.dumps(radar_labels),
                           radar_data=json.dumps(radar_data))

@app.route('/add_subject', methods=['POST'])
def add_subject():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    name = request.form['name']
    if name:
        new_subject = Subject(name=name, user_id=session['user_id'])
        db.session.add(new_subject)
        db.session.commit()
        flash('Materia aggiunta con successo!', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/subject/<int:subject_id>')
def view_subject(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != session['user_id']:
        flash('Accesso non autorizzato!', 'error')
        return redirect(url_for('dashboard'))
    
    average = calculate_weighted_average(subject.grades)
    
    # Prepara dati per il grafico di andamento
    grades = Grade.query.filter_by(subject_id=subject_id).order_by(Grade.date).all()
    chart_dates = [g.date.strftime('%Y-%m-%d') for g in grades] if grades else []
    chart_values = [g.value for g in grades] if grades else []
    
    return render_template('subject.html',
                           subject=subject,
                           average=average,
                           chart_dates=json.dumps(chart_dates),
                           chart_values=json.dumps(chart_values))

@app.route('/add_grade/<int:subject_id>', methods=['POST'])
def add_grade(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != session['user_id']:
        flash('Accesso non autorizzato!', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        value = float(request.form['value'])
        weight = float(request.form.get('weight', 1))
        
        # Crea il nuovo voto con data corrente
        new_grade = Grade(
            value=value,
            weight=weight,
            subject_id=subject_id,
            date=datetime.utcnow()  # Data corrente
        )
        
        db.session.add(new_grade)
        db.session.commit()
        flash('Voto aggiunto con successo!', 'success')
    except ValueError:
        flash('Valore non valido!', 'error')
    except Exception as e:
        flash(f'Errore: {str(e)}', 'error')
        app.logger.error(f"Errore salvataggio voto: {str(e)}")
    
    return redirect(url_for('view_subject', subject_id=subject_id))

@app.route('/delete_grade/<int:grade_id>', methods=['POST'])
def delete_grade(grade_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    grade = Grade.query.get_or_404(grade_id)
    subject = Subject.query.get_or_404(grade.subject_id)
    
    if subject.user_id != session['user_id']:
        flash('Accesso non autorizzato!', 'error')
        return redirect(url_for('dashboard'))
    
    db.session.delete(grade)
    db.session.commit()
    flash('Voto eliminato con successo!', 'success')
    return redirect(url_for('view_subject', subject_id=subject.id))

@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    subject = Subject.query.get_or_404(subject_id)
    if subject.user_id != session['user_id']:
        flash('Accesso non autorizzato!', 'error')
        return redirect(url_for('dashboard'))
    
    # Elimina prima tutti i voti associati
    for grade in subject.grades:
        db.session.delete(grade)
    
    db.session.delete(subject)
    db.session.commit()
    flash('Materia eliminata con successo!', 'success')
    return redirect(url_for('dashboard'))

# 8. Debug route
@app.route('/debug_db')
def debug_db():
    try:
        with app.app_context():
            # Ottieni i nomi delle tabelle
            table_names = get_table_names(db.engine)
            user_count = User.query.count()
            subject_count = Subject.query.count()
            grade_count = Grade.query.count()
            
            return (
                f"Database funzionante!<br>"
                f"Tabelle: {table_names}<br>"
                f"Utenti: {user_count}<br>"
                f"Materie: {subject_count}<br>"
                f"Voti: {grade_count}"
            )
    except Exception as e:
        return f"Errore database: {str(e)}"

# 10. Avvio applicazione
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
