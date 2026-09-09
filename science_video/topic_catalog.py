"""Curated daily topics for the educational technology series."""
import secrets

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


def topic_for_day(existing_topics, day_index=0):
    """Return the next catalog topic not already present in the queue."""
    existing = {topic.casefold() for topic in existing_topics}
    for offset in range(len(TOPICS)):
        topic = TOPICS[(day_index + offset) % len(TOPICS)]
        if topic.casefold() not in existing:
            return topic
    raise ValueError("All catalog topics are already queued. Add a new topic to topic_catalog.py.")