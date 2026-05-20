#!/usr/bin/env python3
"""
SeePhys Pro baseline runner.

Reads parquet shards under data/SeePhysPro/data/{level}/{split}-*.parquet,
calls a multimodal Chat Completions endpoint per row, and writes:

  output/<run_name>/prediction.csv          (testmini, public leaderboard)
  output/<run_name>/prediction_private.csv  (test, private leaderboard)
  output/<run_name>/raw_responses.jsonl     (full model output, for debugging)

CSV columns required by Codabench: question_id, prediction, reasoning.

Resumable: re-running skips question_ids that already exist in raw_responses.jsonl.
Concurrency via threads. Each request is wrapped in retry-with-backoff.

Examples
--------
# Public leaderboard only (testmini, 830 rows):
python scripts/run_baseline.py --split testmini --model gpt-4o-mini

# Both public and private (testmini + test, 4150 rows total):
python scripts/run_baseline.py --split both --model gpt-4o

# Smoke test on level1 testmini, 5 rows, 1 worker:
python scripts/run_baseline.py --split testmini --levels level1 --limit 5 --workers 1
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "SeePhysPro" / "data"
OUTPUT_DIR = ROOT / "output"

ALL_LEVELS = ["level1", "level2", "level3", "level4", "level5"]

SYSTEM_PROMPT = (
    "You are an expert physics tutor. For each problem, you must:\n"
    "1. Carefully read the text and inspect any provided diagram(s).\n"
    "2. Identify all known/unknown quantities and the physical principles involved.\n"
    "3. Reason step-by-step with explicit equations.\n"
    "4. Track units and report numeric answers to a sensible precision.\n"
    "5. End with a clearly delimited final answer.\n"
    "\n"
    "Output STRICTLY in this format:\n"
    "<reasoning>\n"
    "...your full chain of reasoning here...\n"
    "</reasoning>\n"
    "<answer>...the final answer only (no units unless asked, no extra text)...</answer>\n"
)

USER_PROMPT_TEMPLATE = (
    "Solve the following physics problem.\n\n"
    "{problem}\n\n"
    "Remember: produce exactly one <reasoning>...</reasoning> block followed by "
    "exactly one <answer>...</answer> block. The final answer should be concise "
    "(a number, expression, or option letter(s) like 'BD')."
)


# ---------- I/O helpers ----------------------------------------------------


def encode_image_to_data_url(img_field: Any) -> str | None:
    """img_field is dict {bytes, path} or PIL.Image or bytes. Return base64 data URL."""
    if img_field is None:
        return None

    raw: bytes | None = None
    fmt = "png"

    if isinstance(img_field, dict):
        raw = img_field.get("bytes")
        path = img_field.get("path") or ""
        if path.lower().endswith((".jpg", ".jpeg")):
            fmt = "jpeg"
        elif path.lower().endswith(".webp"):
            fmt = "webp"
    elif isinstance(img_field, (bytes, bytearray)):
        raw = bytes(img_field)
    elif isinstance(img_field, Image.Image):
        buf = io.BytesIO()
        img_field.save(buf, format="PNG")
        raw = buf.getvalue()

    if not raw:
        return None

    # Optional: cap max dimension to control token cost
    try:
        im = Image.open(io.BytesIO(raw))
        max_side = 1280
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=85)
            raw = buf.getvalue()
            fmt = "jpeg"
    except Exception:
        pass

    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/{fmt};base64,{b64}"


def parse_response(text: str) -> tuple[str, str]:
    """Extract <answer> and <reasoning> from model output. Robust to missing tags."""
    import re

    reasoning = ""
    answer = ""

    m_r = re.search(r"<reasoning>(.*?)</reasoning>", text, re.DOTALL | re.IGNORECASE)
    if m_r:
        reasoning = m_r.group(1).strip()

    m_a = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    if m_a:
        answer = m_a.group(1).strip()

    if not answer:
        # Fallbacks: "Final Answer:", "Answer:", or last non-tag, non-empty line.
        m = re.search(r"(?:final\s*answer|answer)\s*[:：]\s*(.+)", text, re.IGNORECASE)
        if m:
            answer = m.group(1).strip().splitlines()[0].strip()
        else:
            cleaned = re.sub(r"</?(?:reasoning|answer)>", "", text, flags=re.IGNORECASE)
            lines = [ln.strip() for ln in cleaned.strip().splitlines() if ln.strip()]
            answer = lines[-1] if lines else ""

    if not reasoning:
        reasoning = text.strip()

    # Keep reasoning bounded so CSV stays manageable.
    if len(reasoning) > 4000:
        reasoning = reasoning[:4000] + "...[truncated]"
    return answer, reasoning


# ---------- Inference ------------------------------------------------------


def make_client(args):
    from openai import OpenAI

    return OpenAI(
        api_key=args.api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=args.base_url or os.environ.get("OPENAI_BASE_URL"),
    )


def call_model(client, args, problem: str, images: list[Any]) -> str:
    """Single API call with text + image content. Returns raw text."""
    content: list[dict[str, Any]] = [
        {"type": "text", "text": USER_PROMPT_TEMPLATE.format(problem=problem)}
    ]
    for img in images or []:
        url = encode_image_to_data_url(img)
        if url:
            content.append({"type": "image_url", "image_url": {"url": url}})

    msg = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    last_err = None
    for attempt in range(args.max_retries):
        try:
            resp = client.chat.completions.create(
                model=args.model,
                messages=msg,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:  # broad: network/rate/server
            last_err = e
            sleep = min(2 ** attempt, 30)
            sys.stderr.write(f"[retry {attempt + 1}/{args.max_retries}] {type(e).__name__}: {e}; sleeping {sleep}s\n")
            time.sleep(sleep)
    raise RuntimeError(f"All retries failed: {last_err}")


# ---------- Driver ---------------------------------------------------------


def load_split(level: str, split: str) -> pd.DataFrame:
    f = DATA_DIR / level / f"{split}-00000-of-00001.parquet"
    df = pd.read_parquet(f)
    df["__level__"] = level
    df["__split__"] = split
    return df


def already_done(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    done = set()
    with jsonl_path.open() as f:
        for ln in f:
            try:
                done.add(json.loads(ln)["question_id"])
            except Exception:
                continue
    return done


def run(args):
    run_dir = OUTPUT_DIR / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_path = run_dir / "raw_responses.jsonl"

    levels = args.levels or ALL_LEVELS
    splits_to_run: list[str] = []
    if args.split in ("testmini", "both"):
        splits_to_run.append("testmini")
    if args.split in ("test", "both"):
        splits_to_run.append("test")

    frames: list[pd.DataFrame] = []
    for level in levels:
        for split in splits_to_run:
            try:
                frames.append(load_split(level, split))
            except FileNotFoundError:
                sys.stderr.write(f"missing: {level}/{split} (skipping)\n")
    if not frames:
        sys.exit("no data loaded")
    df = pd.concat(frames, ignore_index=True)
    if args.limit:
        df = df.head(args.limit)
    print(f"Loaded {len(df)} rows across {len(levels)} levels and splits {splits_to_run}")

    done_ids = already_done(raw_path)
    pending = df[~df["question_id"].isin(done_ids)].reset_index(drop=True)
    print(f"Resume: {len(done_ids)} already done; {len(pending)} pending")

    if args.dry_run:
        print("Dry run; not calling API.")
        return

    client = make_client(args)

    raw_fp = raw_path.open("a")
    completed = 0
    failed = 0
    t0 = time.time()

    def worker(row):
        problem = row.get("problem") or ""
        imgs_field = row.get("images")
        if imgs_field is None:
            images = []
        else:
            try:
                images = list(imgs_field)
            except TypeError:
                images = []
        text = call_model(client, args, problem, images)
        ans, reason = parse_response(text)
        return {
            "question_id": row["question_id"],
            "level": row["__level__"],
            "split": row["__split__"],
            "prediction": ans,
            "reasoning": reason,
            "raw": text,
        }

    rows = pending.to_dict("records")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(worker, r): r["question_id"] for r in rows}
        for fut in as_completed(futures):
            qid = futures[fut]
            try:
                rec = fut.result()
                raw_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                raw_fp.flush()
                completed += 1
            except Exception as e:
                failed += 1
                sys.stderr.write(f"FAIL {qid}: {e}\n{traceback.format_exc()}\n")
                err_rec = {
                    "question_id": qid,
                    "level": "",
                    "split": "",
                    "prediction": "",
                    "reasoning": f"[ERROR] {e}",
                    "raw": "",
                }
                raw_fp.write(json.dumps(err_rec, ensure_ascii=False) + "\n")
                raw_fp.flush()

            if (completed + failed) % 10 == 0:
                dt = time.time() - t0
                rate = (completed + failed) / max(dt, 1e-6)
                remaining = len(rows) - (completed + failed)
                eta = remaining / max(rate, 1e-6)
                print(f"  progress: ok={completed} fail={failed} rate={rate:.2f}/s eta={eta / 60:.1f}m")
    raw_fp.close()
    print(f"Done. ok={completed} fail={failed} elapsed={(time.time() - t0) / 60:.1f}m")

    write_csvs(run_dir)


def write_csvs(run_dir: Path):
    """Aggregate raw_responses.jsonl into prediction.csv (testmini) and prediction_private.csv (test)."""
    raw_path = run_dir / "raw_responses.jsonl"
    if not raw_path.exists():
        print("no raw_responses.jsonl; skipping csv build")
        return
    by_split: dict[str, list[dict[str, str]]] = {"testmini": [], "test": []}
    seen: set[str] = set()
    with raw_path.open() as f:
        for ln in f:
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            qid = rec.get("question_id")
            if not qid or qid in seen:
                continue
            seen.add(qid)
            split = rec.get("split") or ""
            if split not in by_split:
                # If split missing (older logs), infer from question_id
                split = "testmini" if "testmini" in qid else "test"
            by_split[split].append(
                {
                    "question_id": qid,
                    "prediction": rec.get("prediction", ""),
                    "reasoning": rec.get("reasoning", ""),
                }
            )

    public_csv = run_dir / "prediction.csv"
    private_csv = run_dir / "prediction_private.csv"
    for path, rows in [(public_csv, by_split["testmini"]), (private_csv, by_split["test"])]:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["question_id", "prediction", "reasoning"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"wrote {path} ({len(rows)} rows)")

    # Bundle the zip Codabench expects.
    import zipfile

    zpath = run_dir / "submission.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        if public_csv.exists():
            z.write(public_csv, arcname="prediction.csv")
        if private_csv.exists():
            z.write(private_csv, arcname="prediction_private.csv")
    print(f"wrote {zpath}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", default="baseline_v1")
    p.add_argument(
        "--split",
        choices=["testmini", "test", "both"],
        default="testmini",
        help="testmini -> public, test -> private, both -> both",
    )
    p.add_argument("--levels", nargs="*", choices=ALL_LEVELS, help="default: all")
    p.add_argument("--limit", type=int, default=0, help="0 = no limit")
    p.add_argument("--model", default=os.environ.get("MODEL", "gpt-4o-mini"))
    p.add_argument("--api-key", default=None)
    p.add_argument("--base-url", default=None, help="custom OpenAI-compatible base URL")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--max-retries", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--build-csv-only", action="store_true", help="just rebuild csvs from raw_responses.jsonl")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.build_csv_only:
        write_csvs(OUTPUT_DIR / args.run_name)
    else:
        run(args)
