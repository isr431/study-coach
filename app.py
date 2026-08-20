import json
import os
import sqlite3

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
import requests


load_dotenv()
app = Flask(__name__)
DATABASE = "study_coach.db"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-3.7-flash"


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_connection()
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
            completed INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    connection.close()


def request_completion(messages):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None, "The OpenRouter API key is not configured"

    payload = {"model": MODEL, "messages": messages, "temperature": 0.2}

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=30,
        )
        if not response.ok:
            raise ValueError

        content = response.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None, "The OpenRouter request failed"

    return content, None


def request_topic_plan(course_name, syllabus_text):
    messages = [
        {
            "role": "system",
            "content": (
                "Create an ordered study plan from the supplied course material. "
                "Return only a JSON array. Each item must contain a non-empty "
                '"title" and a short non-empty "summary".'
            ),
        },
        {
            "role": "user",
            "content": f"Course: {course_name}\n\nCourse material:\n{syllabus_text}",
        },
    ]

    content, error = request_completion(messages)
    if error:
        return None, error

    try:
        topics = json.loads(content)
        if not isinstance(topics, list) or not topics:
            raise ValueError

        validated_topics = [
            {"title": topic["title"].strip(), "summary": topic["summary"].strip()}
            for topic in topics
        ]
        if not all(topic["title"] and topic["summary"] for topic in validated_topics):
            raise ValueError
    except (AttributeError, KeyError, TypeError, ValueError):
        return None, "The study plan could not be generated"

    return validated_topics, None


def request_explanation(topic_row, question):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a study coach. Answer the student's question about the "
                "selected topic, stay relevant to the supplied course material and "
                "explain the answer clearly."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Course: {topic_row['name']}\n"
                f"Topic: {topic_row['title']}\n"
                f"Topic summary: {topic_row['summary']}\n\n"
                f"Course material:\n{topic_row['syllabus_text']}\n\n"
                f"Question: {question}"
            ),
        },
    ]

    answer, error = request_completion(messages)
    if error:
        return None, error

    return answer.strip(), None


def save_course_and_topics(course_name, syllabus_text, topics):
    connection = get_connection()
    with connection:
        connection.execute("DELETE FROM topic")
        connection.execute("DELETE FROM course")
        cursor = connection.execute(
            "INSERT INTO course (name, syllabus_text) VALUES (?, ?)",
            (course_name, syllabus_text),
        )
        course_id = cursor.lastrowid

        for order_index, topic in enumerate(topics, start=1):
            connection.execute(
                """
                INSERT INTO topic (course_id, title, summary, order_index)
                VALUES (?, ?, ?, ?)
                """,
                (course_id, topic["title"], topic["summary"], order_index),
            )
    connection.close()


def get_progress(connection):
    counts = connection.execute(
        """
        SELECT COUNT(*) AS total, COALESCE(SUM(completed), 0) AS completed
        FROM topic
        """
    ).fetchone()
    total = counts["total"]
    completed = counts["completed"]
    percentage = round(completed / total * 100) if total else 0
    return {"completed": completed, "total": total, "percentage": percentage}


def read_state():
    connection = get_connection()
    course_row = connection.execute("SELECT name FROM course LIMIT 1").fetchone()
    topic_rows = connection.execute(
        "SELECT id, title, summary, completed FROM topic ORDER BY order_index"
    ).fetchall()
    progress = get_progress(connection)
    connection.close()

    topics = [
        {
            "id": row["id"],
            "title": row["title"],
            "summary": row["summary"],
            "completed": bool(row["completed"]),
        }
        for row in topic_rows
    ]
    course = {"name": course_row["name"]} if course_row else None
    return {"course": course, "topics": topics, "progress": progress}


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/setup")
def setup_course():
    course_name = request.form.get("course_name", "").strip()
    syllabus_file = request.files.get("syllabus_file")

    if not course_name:
        return jsonify(error="Course name is required"), 400
    if (
        not syllabus_file
        or not syllabus_file.filename
        or not syllabus_file.filename.lower().endswith(".txt")
    ):
        return jsonify(error="A .txt syllabus file is required"), 400

    try:
        syllabus_text = syllabus_file.read().decode("utf-8").strip()
        if not syllabus_text:
            raise ValueError
    except (OSError, UnicodeDecodeError, ValueError):
        return jsonify(error="The syllabus must contain readable text"), 400

    topics, error = request_topic_plan(course_name, syllabus_text)
    if error:
        return jsonify(error=error), 500

    save_course_and_topics(course_name, syllabus_text, topics)
    return jsonify(read_state()), 201


@app.get("/api/state")
def get_state():
    return jsonify(read_state())


@app.patch("/api/topics/<int:topic_id>")
def update_topic(topic_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("completed"), bool):
        return jsonify(error="A completion status is required"), 400

    connection = get_connection()
    with connection:
        connection.execute(
            "UPDATE topic SET completed = ? WHERE id = ?",
            (int(data["completed"]), topic_id),
        )
    progress = get_progress(connection)
    connection.close()

    return jsonify(progress=progress)


@app.post("/api/chat")
def explain_topic():
    data = request.get_json(silent=True) or {}
    question = data.get("question")

    if not isinstance(question, str) or not question.strip():
        return jsonify(error="A question is required"), 400

    connection = get_connection()
    topic_row = connection.execute(
        """
        SELECT topic.title, topic.summary, course.name, course.syllabus_text
        FROM topic
        JOIN course ON course.id = topic.course_id
        WHERE topic.id = ?
        """,
        (data.get("topic_id"),),
    ).fetchone()
    connection.close()

    if not topic_row:
        return jsonify(error="Topic not found"), 404

    answer, error = request_explanation(topic_row, question.strip())
    if error:
        return jsonify(error=error), 500

    return jsonify(answer=answer)


init_db()


if __name__ == "__main__":
    app.run(debug=True)
