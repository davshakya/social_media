"""Curated daily topics for the educational technology series."""
import secrets
import json
import sqlite3
from pathlib import Path

TOPICS = (
    "What actually happens when Python runs a line of code?",
    "What is a Python list, and when should you use one?",
    "Why do Python dictionaries make lookups fast?",
    "What is a function, and how does it make code reusable?",
    "What is an API, explained with a practical example?",
    "What is debugging, and how can you find a bug faster?",
    "What is version control, and why does Git matter?",
    "What is a database index, and why does it speed up search?",
    "What is machine learning in one practical example?",
    "What is the difference between training data and test data?",
    "Why can a machine learning model overfit?",
    "What is a feature in data science?",
    "What is classification versus regression?",
    "What does accuracy mean, and when can it mislead you?",
    "What is a confusion matrix used for?",
    "How does a recommendation system learn your preferences?",
    "What is a neural network neuron?",
    "What is an embedding in AI?",
    "What is a large language model doing with your prompt?",
    "Why do AI models sometimes hallucinate?",
    "What is prompt engineering with a useful before-and-after?",
    "What is retrieval augmented generation?",
    "How can you protect private data when using AI tools?",
    "What is data cleaning and why does it matter?",
    "Why are charts useful for finding patterns in data?",
    "What is the difference between correlation and causation?",
    "What is a CSV file and how can Python analyze it?",
    "What is automation and what should you automate first?",
    "What is Big O notation without confusing math?",
    "How do you turn a coding idea into a small project?",
)


def random_topic():
    """Return a random topic from the curated educational series."""
    return secrets.choice(TOPICS)


def reserve_fresh_topic(output):
    """Persist selections, including failed attempts, to avoid repeating topics."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output / "topic_history.sqlite3", timeout=30) as db:
        db.execute("CREATE TABLE IF NOT EXISTS used_topics (topic TEXT PRIMARY KEY)")
        db.execute("BEGIN IMMEDIATE")
        for path in output.glob("*/storyboard.json"):
            try:
                topic = json.loads(path.read_text(encoding="utf-8"))["topic"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if isinstance(topic, str):
                db.execute("INSERT OR IGNORE INTO used_topics VALUES (?)", (topic.casefold(),))
        used = {row[0] for row in db.execute("SELECT topic FROM used_topics")}
        available = [topic for topic in TOPICS if topic.casefold() not in used]
        if not available:
            raise ValueError("All catalog topics have been used. Add topics to science_video/topic_catalog.py or supply a new --topic.")
        topic = secrets.choice(available)
        db.execute("INSERT INTO used_topics VALUES (?)", (topic.casefold(),))
        return topic


def topic_for_day(existing_topics, day_index=0):
    """Return the next catalog topic not already present in the queue."""
    existing = {topic.casefold() for topic in existing_topics}
    for offset in range(len(TOPICS)):
        topic = TOPICS[(day_index + offset) % len(TOPICS)]
        if topic.casefold() not in existing:
            return topic
    raise ValueError("All catalog topics are already queued. Add a new topic to topic_catalog.py.")
