from pathlib import Path
from flask import Flask, render_template
import sqlite3

app = Flask(__name__)
DATABASE = Path(__file__).with_name("study_coach.db")

def init_db():
    connection = sqlite3.connect(DATABASE)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS course (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            syllabus_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
            FOREIGN KEY (course_id) REFERENCES course (id) ON DELETE CASCADE
        );
        """
    )
    connection.close()

@app.route("/")
def index():
    return render_template("index.html")

init_db()

if __name__ == "__main__":
    app.run(debug=True)