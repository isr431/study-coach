import json
import os
from pathlib import Path
import sqlite3

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
import requests


load_dotenv()
app = Flask(__name__)
DATABASE = Path(__file__).with_name("study_coach.db")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-3.7-flash"


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")
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
            completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
            FOREIGN KEY (course_id) REFERENCES course (id) ON DELETE CASCADE
        );
        """
    )
    connection.close()


def request_topic_plan(course_name, syllabus_text):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None, "The OpenRouter API key is not configured"

    payload = {
        "model": MODEL,
        "messages": [
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
        ],
        "temperature": 0.2,
    }

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
        topics = json.loads(content)

        if not isinstance(topics, list) or not topics:
            raise ValueError

        validated_topics = []
        for topic in topics:
            if not isinstance(topic, dict):
                raise ValueError

            title = topic.get("title")
            summary = topic.get("summary")
            if not isinstance(title, str) or not isinstance(summary, str):
                raise ValueError

            title = title.strip()
            summary = summary.strip()
            if not title or not summary:
                raise ValueError

            validated_topics.append({"title": title, "summary": summary})
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None, "The study plan could not be generated"

    return validated_topics, None


def save_course_and_topics(course_name, syllabus_text, topics):
    connection = get_connection()
    saved_topics = []

    try:
        with connection:
            connection.execute("DELETE FROM topic")
            connection.execute("DELETE FROM course")
            cursor = connection.execute(
                "INSERT INTO course (name, syllabus_text) VALUES (?, ?)",
                (course_name, syllabus_text),
            )
            course_id = cursor.lastrowid

            for order_index, topic in enumerate(topics, start=1):
                cursor = connection.execute(
                    """
                    INSERT INTO topic (course_id, title, summary, order_index)
                    VALUES (?, ?, ?, ?)
                    """,
                    (course_id, topic["title"], topic["summary"], order_index),
                )
                saved_topics.append(
                    {
                        "id": cursor.lastrowid,
                        "title": topic["title"],
                        "summary": topic["summary"],
                        "order_index": order_index,
                        "completed": False,
                    }
                )
    finally:
        connection.close()

    return {"id": course_id, "name": course_name}, saved_topics


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

    try:
        course, saved_topics = save_course_and_topics(
            course_name, syllabus_text, topics
        )
    except sqlite3.Error:
        return jsonify(error="The course and study plan could not be saved"), 500

    return jsonify(course=course, topics=saved_topics), 201


init_db()


if __name__ == "__main__":
    app.run(debug=True)
