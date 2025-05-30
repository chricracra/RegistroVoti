from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Effettua l'accesso per accedere a questa pagina"
login_manager.login_message_category = "info"
csrf = CSRFProtect(app)

# Modelli
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    theme_preference = db.Column(db.String(10), default='light')
    subjects = db.relationship('Subject', backref='user', lazy=True)
    grades = db.relationship('Grade', backref='user', lazy=True)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    grades = db.relationship('Grade', backref='subject', lazy=True, cascade="all, delete-orphan")
    
    @property
    def avg(self):
        if not self.grades:
            return 0
        total = sum(grade.value * grade.weight for grade in self.grades)
        weights = sum(grade.weight for grade in self.grades)
        return round(total / weights, 2) if weights else 0

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, default=1.0)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Setup Login Manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def home():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    subjects = Subject.query.filter_by(user_id=current_user.id).all()
    overall_avg = round(sum(subject.avg for subject in subjects) / len(subjects), 2) if subjects else 0
    return render_template('dashboard.html', subjects=subjects, overall_avg=overall_avg)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Username o password non validi', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username già registrato', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registrazione completata! Effettua il login', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_subject', methods=['POST'])
@login_required
def add_subject():
    name = request.form['name']
    new_subject = Subject(name=name, user_id=current_user.id)
    db.session.add(new_subject)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_subject/<int:id>')
@login_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    if subject.user_id == current_user.id:
        db.session.delete(subject)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/subject/<int:id>')
@login_required
def subject(id):
    subject = Subject.query.get_or_404(id)
    if subject.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    return render_template('subject.html', subject=subject)

@app.route('/add_grade', methods=['POST'])
@login_required
def add_grade():
    subject_id = request.form['subject_id']
    value = float(request.form['value'])
    weight = float(request.form.get('weight', 1.0))
    
    new_grade = Grade(
        value=value, 
        weight=weight, 
        subject_id=subject_id,
        user_id=current_user.id
    )
    db.session.add(new_grade)
    db.session.commit()
    return redirect(url_for('subject', id=subject_id))

@app.route('/delete_grade/<int:grade_id>')
@login_required
def delete_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    if grade.user_id == current_user.id:
        subject_id = grade.subject_id
        db.session.delete(grade)
        db.session.commit()
        return redirect(url_for('subject', id=subject_id))
    return redirect(url_for('dashboard'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    try:
        # Elimina tutti i dati correlati all'utente
        Grade.query.filter_by(user_id=current_user.id).delete()
        Subject.query.filter_by(user_id=current_user.id).delete()
        
        # Elimina l'utente
        user = User.query.get(current_user.id)
        db.session.delete(user)
        db.session.commit()
        
        logout_user()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/update_theme', methods=['POST'])
@login_required
def update_theme():
    theme = request.json.get('theme')
    if theme in ['light', 'dark']:
        current_user.theme_preference = theme
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route('/health')
def health_check():
    try:
        db.session.execute("SELECT 1")
        return jsonify(status="OK"), 200
    except:
        return jsonify(status="DB Error"), 500

# Security headers
@app.after_request
def add_security_headers(resp):
    resp.headers['Content-Security-Policy'] = "default-src 'self'"
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
