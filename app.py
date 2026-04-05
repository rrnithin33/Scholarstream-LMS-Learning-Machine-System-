from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_bcrypt import Bcrypt
import os
import pymysql
import sqlite3


pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = 'scholarstream_secret_key'

conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()

cursor.executescript('''
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
''')

conn.commit()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT
)
''')
conn.commit()

bcrypt = Bcrypt(app)

# Ensure upload directory exists
UPLOAD_FOLDER = os.path.join('static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
        g.user = cursor.fetchone()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, email, hashed_password, role)
            )
            conn.commit()

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            flash(f'Error: {e}', 'danger')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password_candidate = request.form['password']
        
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        
        if user and bcrypt.check_password_hash(user[3], password_candidate):
            session['user_id'] = user[0]
            session['role'] = user[4]
            flash('You are now logged in', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid login', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not g.user:
        return redirect(url_for('login'))

    role = g.user[4]
    user_id = g.user[0]

    # Admin
    if role == 'admin':
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

        return render_template('admin_dashboard.html', user=g.user, users=users)

    # Instructor
    elif role == 'instructor':
        cursor.execute("SELECT * FROM courses WHERE instructor_id=?", (user_id,))
        courses = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) FROM enrollments e
            JOIN courses c ON e.course_id = c.id
            WHERE c.instructor_id=?
        """, (user_id,))
        enroll_count = cursor.fetchone()[0]

        return render_template('instructor_dashboard.html',
                               user=g.user,
                               courses=courses,
                               enroll_count=enroll_count)

    # Student
    else:
        cursor.execute("""
            SELECT c.*, e.enrolled_at
            FROM courses c
            JOIN enrollments e ON c.id = e.course_id
            WHERE e.student_id=?
        """, (user_id,))
        enrolled_courses = cursor.fetchall()

        cursor.execute("""
            SELECT * FROM courses
            WHERE id NOT IN (
                SELECT course_id FROM enrollments WHERE student_id=?
            )
        """, (user_id,))
        all_courses = cursor.fetchall()

        return render_template('student_dashboard.html',
                               user=g.user,
                               enrolled_courses=enrolled_courses,
                               all_courses=all_courses)

@app.route('/course/new', methods=['GET', 'POST'])
def new_course():
    if not g.user or g.user['role'] != 'instructor':
        flash('Instructors only.', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        thumbnail = request.files.get('thumbnail')
        
        thumbnail_filename = None
        if thumbnail and allowed_file(thumbnail.filename):
            from werkzeug.utils import secure_filename
            thumbnail_filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename))
            
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO courses (title, description, instructor_id, thumbnail) VALUES (%s, %s, %s, %s)", 
                    (title, description, g.user['id'], thumbnail_filename))
        mysql.connection.commit()
        cur.close()
        flash('Course created successfully!', 'success')
        return redirect(url_for('dashboard'))
            
    return render_template('instructor/new_course.html')

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    if not g.user:
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE id = %s", (course_id,))
    course = cur.fetchone()
    
    if not course:
        cur.close()
        flash('Course not found', 'danger')
        return redirect(url_for('dashboard'))
        
    # Lessons
    cur.execute("SELECT * FROM lessons WHERE course_id = %s ORDER BY lesson_order", (course_id,))
    lessons = cur.fetchall()
    
    # Quizzes
    cur.execute("SELECT * FROM quizzes WHERE course_id = %s", (course_id,))
    quizzes = cur.fetchall()
    
    # Assignments
    cur.execute("SELECT * FROM assignments WHERE course_id = %s", (course_id,))
    assignments = cur.fetchall()
    
    # If student, check enrollment
    is_enrolled = False
    if g.user['role'] == 'student':
        cur.execute("SELECT * FROM enrollments WHERE student_id = %s AND course_id = %s", (g.user['id'], course_id))
        is_enrolled = cur.fetchone() is not None
        
    cur.close()
    
    if g.user['role'] == 'instructor' and course['instructor_id'] == g.user['id']:
        return render_template('instructor/course_detail.html', course=course, lessons=lessons, quizzes=quizzes, assignments=assignments)
    elif g.user['role'] == 'student' and is_enrolled:
        return render_template('student/course_view.html', course=course, lessons=lessons, quizzes=quizzes, assignments=assignments)
    else:
        return render_template('course_landing.html', course=course, is_enrolled=is_enrolled)

@app.route('/course/<int:course_id>/lesson/add', methods=['POST'])
def add_lesson(course_id):
    if not g.user or g.user['role'] != 'instructor':
        return redirect(url_for('dashboard'))
        
    title = request.form['title']
    content_type = request.form['content_type']
    content_file = request.files.get('content_file')
    
    filename = None
    if content_file and allowed_file(content_file.filename):
        from werkzeug.utils import secure_filename
        filename = secure_filename(content_file.filename)
        content_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) as count FROM lessons WHERE course_id = %s", (course_id,))
    count = cur.fetchone()['count']
    cur.execute("INSERT INTO lessons (course_id, title, content_type, content_url, lesson_order) VALUES (%s, %s, %s, %s, %s)", 
                (course_id, title, content_type, filename, count + 1))
    mysql.connection.commit()
    cur.close()
    flash('Lesson added!', 'success')
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/enroll/<int:course_id>')
def enroll(course_id):
    if not g.user or g.user['role'] != 'student':
        flash('Login as a student to enroll', 'warning')
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO enrollments (student_id, course_id) VALUES (%s, %s)", (g.user['id'], course_id))
        mysql.connection.commit()
        flash('Enrolled successfully!', 'success')
    except:
        flash('Already enrolled', 'info')
    finally:
        cur.close()
        
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/course/<int:course_id>/quiz/new', methods=['GET', 'POST'])
def new_quiz(course_id):
    if not g.user or g.user['role'] != 'instructor':
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form['title']
        passing_score = request.form['passing_score']
        
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO quizzes (course_id, title, passing_score) VALUES (%s, %s, %s)", (course_id, title, passing_score))
        mysql.connection.commit()
        quiz_id = cur.lastrowid
        cur.close()
        flash('Quiz created! Now add some questions.', 'success')
        return redirect(url_for('quiz_builder', quiz_id=quiz_id))
        
    return render_template('instructor/new_quiz.html', course_id=course_id)

@app.route('/quiz/<int:quiz_id>/builder', methods=['GET', 'POST'])
def quiz_builder(quiz_id):
    if not g.user or g.user['role'] != 'instructor':
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        question_text = request.form['question_text']
        options = [request.form['opt1'], request.form['opt2'], request.form['opt3'], request.form['opt4']]
        import json
        options_json = json.dumps(options)
        correct_answer = request.form['correct_answer']
        
        cur.execute("INSERT INTO questions (quiz_id, question_text, options, correct_answer) VALUES (%s, %s, %s, %s)", 
                    (quiz_id, question_text, options_json, correct_answer))
        mysql.connection.commit()
        flash('Question added!', 'success')
        
    cur.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cur.fetchone()
    cur.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    cur.close()
    
    return render_template('instructor/quiz_builder.html', quiz=quiz, questions=questions)

@app.route('/course/<int:course_id>/assignment/new', methods=['GET', 'POST'])
def new_assignment(course_id):
    if not g.user or g.user['role'] != 'instructor':
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date'].replace('T', ' ')
        
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO assignments (course_id, title, description, due_date) VALUES (%s, %s, %s, %s)", 
                    (course_id, title, description, due_date))
        mysql.connection.commit()
        cur.close()
        flash('Assignment added!', 'success')
        return redirect(url_for('course_detail', course_id=course_id))
        
    return render_template('instructor/new_assignment.html', course_id=course_id)

@app.route('/quiz/<int:quiz_id>/take', methods=['GET', 'POST'])
def take_quiz(quiz_id):
    if not g.user or g.user['role'] != 'student':
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cur.fetchone()
    cur.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    import json
    for q in questions:
        q['options'] = json.loads(q['options'])
        
    if request.method == 'POST':
        score = 0
        for q in questions:
            selected = request.form.get(f'q_{q["id"]}')
            if selected == q['correct_answer']:
                score += 1
        
        final_score = int((score / len(questions)) * 100) if questions else 0
        status = 'pass' if final_score >= quiz['passing_score'] else 'fail'
        
        cur.execute("INSERT INTO quiz_attempts (student_id, quiz_id, score, status) VALUES (%s, %s, %s, %s)", 
                    (g.user['id'], quiz_id, final_score, status))
        mysql.connection.commit()
        cur.close()
        flash(f'Quiz submitted! Your score: {final_score}% ({status})', 'success' if status == 'pass' else 'warning')
        return redirect(url_for('course_detail', course_id=quiz['course_id']))
        
    cur.close()
    return render_template('student/take_quiz.html', quiz=quiz, questions=questions)

@app.route('/assignment/<int:assignment_id>/submit', methods=['POST'])
def submit_assignment(assignment_id):
    if not g.user or g.user['role'] != 'student':
        return redirect(url_for('login'))
        
    submission_file = request.files.get('submission_file')
    if submission_file and allowed_file(submission_file.filename):
        from werkzeug.utils import secure_filename
        filename = secure_filename(submission_file.filename)
        submission_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO assignment_submissions (assignment_id, student_id, file_path) VALUES (%s, %s, %s)", 
                    (assignment_id, g.user['id'], filename))
        mysql.connection.commit()
        
        # Simple Logic: For "Peer-Review", let's just mark it as submitted. 
        # In a real app we'd have a pool of submissions for students to review.
        cur.close()
        flash('Assignment submitted successfully!', 'success')
    else:
        flash('Invalid file type', 'danger')
        
    return redirect(request.referrer)

@app.route('/assignment/<int:assignment_id>/submissions')
def view_submissions(assignment_id):
    if not g.user or g.user['role'] not in ['instructor', 'admin', 'student']:
        return redirect(url_for('login'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT s.*, u.username, a.title as a_title FROM assignment_submissions s JOIN users u ON s.student_id = u.id JOIN assignments a ON s.assignment_id = a.id WHERE s.assignment_id = %s", (assignment_id,))
    submissions = cur.fetchall()
    
    cur.execute("SELECT * FROM assignments WHERE id = %s", (assignment_id,))
    assignment = cur.fetchone()
    cur.close()
    
    return render_template('view_submissions.html', submissions=submissions, assignment=assignment)

@app.route('/submission/<int:submission_id>/review', methods=['POST'])
def review_submission(submission_id):
    if not g.user or g.user['role'] not in ['instructor', 'student']:
        return redirect(url_for('login'))
        
    grade = request.form['grade']
    comments = request.form['comments']
    
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO assignment_reviews (submission_id, reviewer_id, grade, comments) VALUES (%s, %s, %s, %s)", 
                (submission_id, g.user['id'], grade, comments))
    mysql.connection.commit()
    cur.close()
    flash('Review submitted!', 'success')
    return redirect(request.referrer)

@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    if not g.user or g.user['role'] != 'admin':
        flash('Admins only.', 'danger')
        return redirect(url_for('dashboard'))
    
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        role = request.form['role']
        
        try:
            cur.execute("UPDATE users SET username = %s, email = %s, role = %s WHERE id = %s", 
                        (username, email, role, user_id))
            mysql.connection.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error: {e}', 'danger')
    
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_to_edit = cur.fetchone()
    cur.close()
    
    if not user_to_edit:
        flash('User not found', 'danger')
        return redirect(url_for('dashboard'))
        
    return render_template('admin/edit_user.html', user_to_edit=user_to_edit)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    print(f"--- ATTEMPTING TO DELETE USER {user_id} ---")
    if not g.user or g.user['role'] != 'admin':
        flash('Admins only.', 'danger')
        return redirect(url_for('dashboard'))
    
    if g.user['id'] == user_id:
        flash('You cannot delete yourself!', 'warning')
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        mysql.connection.commit()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    finally:
        cur.close()
        
    return redirect(url_for('dashboard'))

@app.route('/course/<int:course_id>/edit', methods=['GET', 'POST'])
def edit_course(course_id):
    if not g.user or g.user['role'] != 'instructor':
        flash('Instructors only.', 'danger')
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE id = %s", (course_id,))
    course = cur.fetchone()
    
    if not course or course['instructor_id'] != g.user['id']:
        cur.close()
        flash('Course not found or unauthorized', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        thumbnail = request.files.get('thumbnail')
        
        thumbnail_filename = course['thumbnail']
        if thumbnail and allowed_file(thumbnail.filename):
            from werkzeug.utils import secure_filename
            thumbnail_filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename))
            
        cur.execute("UPDATE courses SET title = %s, description = %s, thumbnail = %s WHERE id = %s", 
                    (title, description, thumbnail_filename, course_id))
        mysql.connection.commit()
        cur.close()
        flash('Course updated successfully!', 'success')
        return redirect(url_for('course_detail', course_id=course_id))
        
    cur.close()
    return render_template('instructor/edit_course.html', course=course)

@app.route('/course/<int:course_id>/delete', methods=['POST'])
def delete_course(course_id):
    if not g.user or g.user['role'] != 'instructor':
        flash('Instructors only.', 'danger')
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM courses WHERE id = %s", (course_id,))
    course = cur.fetchone()
    
    if not course or course['instructor_id'] != g.user['id']:
        cur.close()
        flash('Course not found or unauthorized', 'danger')
        return redirect(url_for('dashboard'))
        
    try:
        cur.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        mysql.connection.commit()
        flash('Course deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    finally:
        cur.close()
        
    return redirect(url_for('dashboard'))

@app.route('/lesson/<int:lesson_id>/edit', methods=['GET', 'POST'])
def edit_lesson(lesson_id):
    if not g.user or g.user['role'] != 'instructor':
        flash('Instructors only.', 'danger')
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT l.*, c.instructor_id FROM lessons l JOIN courses c ON l.course_id = c.id WHERE l.id = %s", (lesson_id,))
    lesson = cur.fetchone()
    
    if not lesson or lesson['instructor_id'] != g.user['id']:
        cur.close()
        flash('Lesson not found or unauthorized', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form['title']
        content_type = request.form['content_type']
        content_file = request.files.get('content_file')
        
        filename = lesson['content_url']
        if content_file and allowed_file(content_file.filename):
            from werkzeug.utils import secure_filename
            filename = secure_filename(content_file.filename)
            content_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        cur.execute("UPDATE lessons SET title = %s, content_type = %s, content_url = %s WHERE id = %s", 
                    (title, content_type, filename, lesson_id))
        mysql.connection.commit()
        cur.close()
        flash('Lesson updated successfully!', 'success')
        return redirect(url_for('course_detail', course_id=lesson['course_id']))
        
    cur.close()
    return render_template('instructor/edit_lesson.html', lesson=lesson)

@app.route('/lesson/<int:lesson_id>/delete', methods=['POST'])
def delete_lesson(lesson_id):
    if not g.user or g.user['role'] != 'instructor':
        flash('Instructors only.', 'danger')
        return redirect(url_for('dashboard'))
        
    cur = mysql.connection.cursor()
    cur.execute("SELECT l.course_id, c.instructor_id FROM lessons l JOIN courses c ON l.course_id = c.id WHERE l.id = %s", (lesson_id,))
    lesson = cur.fetchone()
    
    if not lesson or lesson['instructor_id'] != g.user['id']:
        cur.close()
        flash('Lesson not found or unauthorized', 'danger')
        return redirect(url_for('dashboard'))
        
    course_id = lesson['course_id']
    cur.execute("DELETE FROM lessons WHERE id = %s", (lesson_id,))
    mysql.connection.commit()
    cur.close()
    flash('Lesson deleted', 'success')
    return redirect(url_for('course_detail', course_id=course_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


