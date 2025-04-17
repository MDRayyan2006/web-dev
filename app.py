from flask import Flask, render_template, request, redirect, jsonify, session, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'


db_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(db_dir, "test.db")


os.makedirs(db_dir, exist_ok=True)

# Configure SQLAlchemy with absolute path and additional settings
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'timeout': 30  
    }
}

db = SQLAlchemy(app)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shared_with = db.Column(db.String(500), nullable=True)  # Store shared user IDs as comma-separated string
    file_path = db.Column(db.String(255), nullable=True)  # Add this line to store file paths
    status = db.Column(db.String(50), default='pending')
    priority = db.Column(db.String(20), default='medium')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Specify the login view

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Add sharing functionality
@app.route('/share_task/<int:id>', methods=['POST'])
@login_required
def share_task(id):
    try:
        task = Todo.query.get_or_404(id)
        
        if task.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'You are not authorized to share this task.'})

        share_with_username = request.form.get('share_with')
        if not share_with_username or share_with_username.strip() == '':
            return jsonify({'success': False, 'error': 'Please enter a username to share with.'})

        user_to_share = User.query.filter_by(username=share_with_username).first()
        if not user_to_share:
            return jsonify({'success': False, 'error': f'User "{share_with_username}" not found.'})

        if user_to_share.id == current_user.id:
            return jsonify({'success': False, 'error': 'You cannot share a task with yourself.'})

        # Initialize shared_with if None
        if task.shared_with is None:
            task.shared_with = ''

        # Handle the shared_with field
        shared_with = [s for s in task.shared_with.split(',') if s]  # Filter out empty strings
        if str(user_to_share.id) not in shared_with:
            shared_with.append(str(user_to_share.id))
            task.shared_with = ','.join(shared_with)
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'Task is already shared with {user_to_share.username}.'})

    except Exception as e:
        db.session.rollback()
        print(f"Error sharing task: {str(e)}")  # For debugging
        return jsonify({'success': False, 'error': 'An error occurred while sharing the task.'})

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'docx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        content = request.form['content']
        task_file = request.files.get('task_file')
        file_path = None

        if task_file and allowed_file(task_file.filename):
            filename = secure_filename(task_file.filename)
            # Create a unique filename to avoid conflicts
            unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            
            # Ensure the upload directory exists
            upload_dir = os.path.join(app.static_folder, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save the file and store only the filename in the database
            task_file.save(os.path.join(upload_dir, unique_filename))
            file_path = unique_filename

        try:
            new_task = Todo(content=content, file_path=file_path, user_id=current_user.id)
            db.session.add(new_task)
            db.session.commit()
            flash('Task added successfully')
            return redirect('/')
        except Exception as e:
            db.session.rollback()
            print(f"Error adding task: {e}")  # Debugging output
            flash('There was an issue adding your task')
            return redirect('/')

    # Fetch tasks for GET request
    own_tasks = Todo.query.filter_by(user_id=current_user.id).all()
    shared_tasks = Todo.query.filter(Todo.shared_with.like(f"%{current_user.id}%")).all()

    return render_template('index.html', own_tasks=own_tasks, shared_tasks=shared_tasks)
    
   

@app.route('/delete/<int:id>')
def delete(id):
    task_to_delete = Todo.query.get_or_404(id)

    try:
        db.session.delete(task_to_delete)
        db.session.commit()
        return redirect('/')
    except:
        return 'There was a problem deleting that task'

@app.route('/update/<int:id>', methods=['GET', 'POST'])
def update(id):
    task = Todo.query.get_or_404(id)

    if request.method == 'POST':
        task.content = request.form['content']
        try:
            db.session.commit()
            return redirect('/')
        except:
            return 'There was an issue updating your task'
    
    return render_template('update.html', task=task)

# Share API Endpoint (Optional)
@app.route('/share/<int:id>', methods=['GET'])
def share(id):
    task = Todo.query.get_or_404(id)
    share_text = f"Check out this task: '{task.content}' from TaskMaster!"
    
    return jsonify({"message": share_text})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and password == user.password:  # In production, use proper password hashing
            login_user(user)
            return redirect('/')
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

# Add registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        # Validate input
        if not username or not password or not email:
            flash('All fields are required')
            return redirect('/register')
        
        # Check if user already exists
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            flash('Username already exists')
            return redirect('/register')
        if email_exists:
            flash('Email already registered')
            return redirect('/register')
        
        new_user = User(username=username, password=password, email=email)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.')
            return redirect('/login')
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")  # For debugging
            flash('Registration failed. Please try again.')
            return redirect('/register')
            
    return render_template('register.html')

# Add these imports at the top
from datetime import datetime

# Add Message model after your existing models
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(255))
    file_type = db.Column(db.String(100))
    original_filename = db.Column(db.String(255))

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_upload_directory():
    upload_path = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_path):
        os.makedirs(upload_path)

@app.route('/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    ensure_upload_directory()
    other_user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        content = request.form.get('message', '')
        file = request.files.get('file')
        
        message = Message(
            sender_id=current_user.id,
            receiver_id=user_id,
            content=content
        )
        
        if file and file.filename:
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_path = f"{timestamp}_{filename}"
                
                try:
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_path))
                    message.file_path = file_path
                    message.file_type = file.content_type
                    message.original_filename = filename
                except Exception as e:
                    flash(f'Error uploading file: {str(e)}')
                    return redirect(url_for('chat', user_id=user_id))
            else:
                flash('Invalid file type')
                return redirect(url_for('chat', user_id=user_id))
        
        try:
            db.session.add(message)
            db.session.commit()
            return redirect(url_for('chat', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error sending message: {str(e)}')
            return redirect(url_for('chat', user_id=user_id))

    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    return render_template('chat.html', other_user=other_user, messages=messages)

def init_db():
    """Initialize the database with default data."""
    import time
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    import atexit

    max_retries = 3
    retry_delay = 1  # seconds

    def cleanup():
        try:
            db.session.remove()
        except:
            pass

    atexit.register(cleanup)

    with app.app_context():
        for attempt in range(max_retries):
            try:
                # Close any existing connections
                db.session.remove()
                engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
                engine.dispose()

                if os.path.exists(db_path):
                    try:
                        # Test if database is accessible using proper text() wrapper
                        db.session.execute(text('SELECT 1'))
                        print("Existing database is accessible")
                        return True
                    except Exception as e:
                        print(f"Database check failed on attempt {attempt + 1}: {e}")
                        time.sleep(retry_delay)
                        
                        # Cleanup connections before attempting to remove file
                        db.session.remove()
                        engine.dispose()
                        
                        try:
                            # Force close any remaining connections
                            db.get_engine().dispose()
                            time.sleep(0.5)  # Give OS time to release file handles
                            
                            if os.path.exists(db_path):
                                os.remove(db_path)
                                print("Successfully removed corrupted database")
                        except OSError as e:
                            print(f"Warning: Could not remove database file: {e}")
                            continue

                # Create all tables
                db.create_all()
                # Verify the database is working
                db.session.execute(text('SELECT 1'))
                db.session.commit()
                print("Database initialized successfully!")
                return True

            except OperationalError as e:
                print(f"Database operation failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue
            except Exception as e:
                print(f"Unexpected error initializing database: {e}")
                return False
            finally:
                try:
                    db.session.remove()
                except:
                    pass

        print(f"Failed to initialize database after {max_retries} attempts")
        return False

if __name__ == "__main__":
    # Initialize the database
    if not init_db():
        print("Failed to initialize database. Please check file permissions and disk space.")
        exit(1)
    
    app.run(debug=True)


