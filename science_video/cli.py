import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from .runtime import ROOT, executable, run
from .storyboard import Storyboard, demo_storyboard, plan


def render_options(parser, *, duration_default="30"):
    parser.add_argument("--output", type=Path, default=ROOT / "videos")
    parser.add_argument("--preview", action="store_true", help="270×480 at 5 fps for a quick complete preview")
    parser.add_argument("--fast", action="store_true", help="Use Blender Eevee for faster rendering")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of Blender scenes to render concurrently; default: 1")
    parser.add_argument("--resolution", choices=("320", "480", "720", "1080"), default="1080",
                        help="Vertical production width; 320 renders 320×568")
    parser.add_argument("--duration", choices=("30", "120", "150", "180"), default=duration_default,
                        help="Video duration in seconds; daily defaults to 120 (2 minutes)")
    parser.add_argument("--topic-image", choices=("none", "openai"),
                        help="Generate a topic-related background image; defaults to TOPIC_IMAGE_PROVIDER")
    parser.add_argument("--topic-image-model", help="Image model; defaults to TOPIC_IMAGE_MODEL")
    voice = parser.add_mutually_exclusive_group()
    voice.add_argument("--silent", action="store_true", help="Explicitly render without speech (labeled preview)")
    voice.add_argument("--voice-dir", type=Path, help="Recorded narration: 01.wav, 02.wav, ... one per scene")
    parser.add_argument("--music", type=Path, help="Optional background music; generated music is the default")


def parser():
    p = argparse.ArgumentParser(description="Hindi 3D Science Video Generator")
    sub = p.add_subparsers(dest="command", required=True)
    from .publishing import add_cli
    add_cli(sub)
    sub.add_parser("doctor", help="Check dependencies and API configuration")
    demo = sub.add_parser("demo", help="Write the included Hindi ice storyboard (no API)")
    demo.add_argument("--out", type=Path, default=ROOT / "examples" / "ice_float.json")
    planner = sub.add_parser("plan", help="Generate a validated Hindi storyboard using AI")
    planner.add_argument("topic")
    planner.add_argument("--out", type=Path, required=True)
    planner.add_argument("--provider", choices=("openai", "openrouter", "groq", "together", "custom", "gemini"),
                         help="AI planner provider; defaults to AI_PLANNER_PROVIDER")
    planner.add_argument("--model", help="Planner model; defaults to AI_PLANNER_MODEL or OPENAI_MODEL")
    planner.add_argument("--duration", choices=("30", "120", "150", "180"), default="30",
                         help="Storyboard duration in seconds")
    validate = sub.add_parser("validate")
    validate.add_argument("storyboard", type=Path)
    generate = sub.add_parser("generate", help="Render a storyboard or plan a supported topic and render")
    source = generate.add_mutually_exclusive_group()
    source.add_argument("--storyboard", type=Path)
    source.add_argument("--topic")
    generate.add_argument("--still", action="store_true", help="Render one diagnostic image per scene")
    generate.add_argument("--provider", choices=("openai", "openrouter", "groq", "together", "custom", "gemini"),
                          help="AI planner provider when --topic is used")
    generate.add_argument("--model", help="Planner model when --topic is used")
    render_options(generate)
    queue = sub.add_parser("queue", help="Manage the SQLite topic schedule")
    queue.add_argument("--db", type=Path, default=ROOT / "topics.sqlite3")
    actions = queue.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add")
    add.add_argument("topic")
    add.add_argument("--due", type=date.fromisoformat, default=date.today())
    actions.add_parser("list")
    retry = actions.add_parser("retry")
    retry.add_argument("id", type=int)
    worker = actions.add_parser("run", help="Process up to --limit due topics, then exit")
    worker.add_argument("--limit", type=int, default=1)
    worker.add_argument("--provider", choices=("openai", "openrouter", "groq", "together", "custom", "gemini"),
                        help="AI planner provider; defaults to AI_PLANNER_PROVIDER")
    worker.add_argument("--model", help="Planner model; defaults to AI_PLANNER_MODEL")
    render_options(worker)
    daily = actions.add_parser("daily", help="Queue one unused educational topic and render today's video")
    daily.add_argument("--provider", choices=("openai", "openrouter", "groq", "together", "custom", "gemini"),
                       help="AI planner provider; defaults to AI_PLANNER_PROVIDER")
    daily.add_argument("--model", help="Planner model; defaults to AI_PLANNER_MODEL")
    daily.add_argument("--no-upload", action="store_true", help="Render locally without automatic YouTube upload")
    render_options(daily, duration_default="120")
    schedule = actions.add_parser("schedule", help="Add the next educational series topics to the daily queue")
    schedule.add_argument("--days", type=int, default=1, help="Number of daily topics to add")
    schedule.add_argument("--start", type=date.fromisoformat, default=date.today(), help="First due date, YYYY-MM-DD")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    args = parser().parse_args(argv)
    try:
        if args.command == "publish":
            from .publishing import run_cli, redact_error
            try:
                return run_cli(args)
            except Exception as exc:
                print(f"Publishing error: {redact_error(exc)}", file=sys.stderr)
                return 1
        if args.command == "doctor":
            missing = False
            for name in ("blender", "ffmpeg"):
                try:
                    path = executable(name)
                    version = run([path, "--version" if name == "blender" else "-version"]).splitlines()[0]
                    print(f"OK {name}: {path} ({version})")
                except (ValueError, RuntimeError) as exc:
                    print(f"MISSING {exc}")
                    missing = True
            print("OPENAI_API_KEY: " + ("configured" if os.getenv("OPENAI_API_KEY") else "not set; demo/recorded/silent workflows available"))
            from .pipeline import preflight
            try:
                _, _, fonts = preflight()
                print(f"Caption font directory: {fonts}")
            except (ValueError, RuntimeError) as exc:
                print(f"MISSING {exc}")
                missing = True
            return 1 if missing else 0
        if args.command == "demo":
            demo_storyboard().write(args.out)
            print(args.out)
        elif args.command == "validate":
            story = Storyboard.read(args.storyboard)
            print(f"Valid: {len(story.scenes)} Hinglish scenes with English-only captions, {story.duration} seconds")
        elif args.command == "plan":
            plan(args.topic, provider=args.provider, model=args.model, duration=int(args.duration)).write(args.out)
            print(args.out)
        elif args.command == "generate":
            from .pipeline import generate
            if args.storyboard:
                story = Storyboard.read(args.storyboard)
            else:
                topic = args.topic
                if not topic:
                    from .topic_catalog import random_topic
                    topic = random_topic()
                    print(f"Random topic: {topic}", flush=True)
                story = plan(topic, provider=args.provider, model=args.model, duration=int(args.duration))
            print(generate(story, args.output, preview=args.preview, silent=args.silent,
                           voice_dir=args.voice_dir, music=args.music, still=args.still,
                           resolution=int(args.resolution), fast=args.fast, workers=args.workers,
                           topic_image_provider=args.topic_image, topic_image_model=args.topic_image_model))
        elif args.command == "queue":
            from .queue import TopicQueue
            queue = TopicQueue(args.db)
            try:
                if args.action == "add":
                    print(f"Queued topic {queue.add(args.topic, args.due.isoformat())}")
                elif args.action == "list":
                    print(json.dumps(queue.rows(), ensure_ascii=False, indent=2))
                elif args.action == "retry":
                    queue.retry(args.id)
                elif args.action == "schedule":
                    if args.days < 1:
                        raise ValueError("--days must be positive")
                    from .topic_catalog import topic_for_day
                    rows = queue.rows()
                    existing = [row["topic"] for row in rows]
                    for offset in range(args.days):
                        topic = topic_for_day(existing, offset)
                        due = args.start.fromordinal(args.start.toordinal() + offset).isoformat()
                        queue.add(topic, due)
                        existing.append(topic)
                        print(f"Queued {due}: {topic}")
                elif args.action in {"run", "daily"}:
                    if args.action == "run" and args.limit < 1:
                        raise ValueError("--limit must be positive")
                    if args.action == "daily":
                        from .topic_catalog import topic_for_day
                        today = date.today().isoformat()
                        rows = queue.rows()
                        if not any(row["status"] == "pending" and row["due"] <= today for row in rows):
                            existing = [row["topic"] for row in rows]
                            topic = topic_for_day(existing, date.today().toordinal())
                            queue.add(topic, today)
                            print(f"Queued today: {topic}")
                        args.limit = 1
                    from .pipeline import generate, preflight
                    preflight()
                    provider = args.provider or os.getenv("AI_PLANNER_PROVIDER", "gemini")
                    if provider == "gemini":
                        has_key = bool(os.getenv("GEMINI_API_KEY"))
                    else:
                        has_key = bool(os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY"))
                    if not has_key:
                        raise ValueError(f"Queue topic planning requires credentials for {provider}")
                    for _ in range(args.limit):
                        row = queue.claim(date.today().isoformat())
                        if not row:
                            print("No topics due")
                            break
                        try:
                            story = plan(row["topic"], provider=provider, model=args.model,
                                         duration=int(args.duration))
                            video = generate(story, args.output, preview=args.preview,
                                             silent=args.silent, voice_dir=args.voice_dir, music=args.music,
                                             fast=args.fast, workers=args.workers,
                                             topic_image_provider=args.topic_image,
                                             topic_image_model=args.topic_image_model)
                            upload_report = None
                            if args.action == "daily" and not args.no_upload:
                                from .publishing import publish_job, prune_completed_jobs
                                upload_report = publish_job(video, platform="youtube")
                            queue.finish(row["id"], output=video)
                            if upload_report is not None:
                                removed = prune_completed_jobs(args.output, keep=2)
                                print(json.dumps({"youtube": upload_report,
                                                  "removed_jobs": [str(path) for path in removed]},
                                                 ensure_ascii=False, indent=2))
                            print(video)
                        except BaseException as exc:
                            queue.finish(row["id"], error=str(exc))
                            raise
            finally:
                queue.close()
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Job artifacts are retained.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
