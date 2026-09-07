import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from .runtime import ROOT, executable, run
from .storyboard import Storyboard, demo_storyboard, plan


def render_options(parser):
    parser.add_argument("--output", type=Path, default=ROOT / "videos")
    parser.add_argument("--preview", action="store_true", help="270×480 at 5 fps for a quick complete preview")
    parser.add_argument("--fast", action="store_true", help="Use Blender Eevee for faster rendering")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of Blender scenes to render concurrently; default: 1")
    parser.add_argument("--resolution", choices=("480", "720", "1080"), default="1080",
                        help="Vertical production width; 480 renders 480×853")
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
    validate = sub.add_parser("validate")
    validate.add_argument("storyboard", type=Path)
    generate = sub.add_parser("generate", help="Render a storyboard or plan a supported topic and render")
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument("--storyboard", type=Path)
    source.add_argument("--topic")
    generate.add_argument("--still", action="store_true", help="Render one diagnostic image per scene")
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
    render_options(worker)
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
            plan(args.topic).write(args.out)
            print(args.out)
        elif args.command == "generate":
            from .pipeline import generate
            story = Storyboard.read(args.storyboard) if args.storyboard else plan(args.topic)
            print(generate(story, args.output, preview=args.preview, silent=args.silent,
                           voice_dir=args.voice_dir, music=args.music, still=args.still,
                           resolution=int(args.resolution), fast=args.fast, workers=args.workers))
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
                elif args.action == "run":
                    if args.limit < 1:
                        raise ValueError("--limit must be positive")
                    from .pipeline import generate, preflight
                    preflight()
                    if not os.getenv("OPENAI_API_KEY"):
                        raise ValueError("Queue topic planning requires OPENAI_API_KEY")
                    for _ in range(args.limit):
                        row = queue.claim(date.today().isoformat())
                        if not row:
                            print("No topics due")
                            break
                        try:
                            video = generate(plan(row["topic"]), args.output, preview=args.preview,
                                             silent=args.silent, voice_dir=args.voice_dir, music=args.music,
                                             fast=args.fast, workers=args.workers)
                            queue.finish(row["id"], output=video)
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
