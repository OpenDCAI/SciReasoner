#!/usr/bin/env python3
"""
Jury voting layer: run k cheap-key models on the same 830 questions
(single-shot, no caption/critic pipeline) to get independent answers.
Then combine with our pipeline's answer via weighted majority vote.

Each juror's output is cached per (model, question_id) so adding more
jurors or re-running is free; ctrl-C is safe.

Usage
-----
# Run a single juror across testmini
python scripts/run_jury.py --juror gpt-5.5 --workers 30 --run-name v2_pub830 \\
    --base-url $OPENAI_BASE_URL --api-key $OPENAI_API_KEY

# After all jurors done, aggregate into a final voted CSV
python scripts/run_jury.py --aggregate --run-name v2_pub830 \\
    --our-csv prediction_audited.csv \\
    --jurors gpt-5.5 claude-opus-4-6-thinking grok-4
"""

from __future__ import annotations
import argparse, base64, csv, io, json, os, random, re, signal, sys, time, traceback
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "SeePhysPro" / "data"
OUTPUT_DIR = ROOT / "output"


JUROR_SYSTEM = (
    "You are an expert physics problem solver. Read the problem carefully, examine any figure, "
    "reason step by step, and produce a final answer in a strict format."
)

JUROR_USER = """\
Solve this physics problem.

{problem}

Output STRICTLY:
<reasoning>
... step-by-step reasoning ...
</reasoning>
<answer>... final answer only — number, expression, or option letters like "BD" — no extra text ...</answer>
"""


def to_data_url(img_field: Any, max_side: int = 1280) -> str | None:
    if img_field is None:
        return None
    raw: bytes | None = None
    fmt = "png"
    if isinstance(img_field, dict):
        raw = img_field.get("bytes")
        path = (img_field.get("path") or "").lower()
        if path.endswith((".jpg", ".jpeg")):
            fmt = "jpeg"
        elif path.endswith(".webp"):
            fmt = "webp"
    elif isinstance(img_field, (bytes, bytearray)):
        raw = bytes(img_field)
    if not raw:
        return None
    try:
        im = Image.open(io.BytesIO(raw))
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=88)
            raw = buf.getvalue()
            fmt = "jpeg"
    except Exception:
        pass
    return f"data:image/{fmt};base64,{base64.b64encode(raw).decode('ascii')}"


def get_images(row) -> list[Any]:
    f = row.get("images")
    if f is None:
        return []
    try:
        return list(f)
    except TypeError:
        return []


def parse_xml(text: str) -> tuple[str, str]:
    reasoning, answer = "", ""
    m = re.search(r"<reasoning>(.*?)</reasoning>", text, re.DOTALL | re.IGNORECASE)
    if m:
        reasoning = m.group(1).strip()
    m = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    if m:
        answer = m.group(1).strip()
    if not answer:
        m = re.search(r"(?:final\s*answer|answer)\s*[:：]\s*(.+)", text, re.IGNORECASE)
        if m:
            answer = m.group(1).strip().splitlines()[0].strip()
        else:
            cleaned = re.sub(r"</?(?:reasoning|answer)>", "", text, flags=re.IGNORECASE)
            lines = [ln.strip() for ln in cleaned.strip().splitlines() if ln.strip()]
            answer = lines[-1] if lines else ""
    if not reasoning:
        reasoning = text.strip()
    return answer, reasoning


def normalize_answer(ans: str) -> str:
    s = (ans or "").strip()
    s = re.sub(r"</?(reasoning|answer)>", "", s, flags=re.I)
    s = re.sub(r"^\s*(?:final\s+answer|answer)\s*[:：]\s*", "", s, flags=re.I)
    m = re.fullmatch(r"\s*\\boxed\{(.+)\}\s*", s, re.S)
    if m:
        s = m.group(1)
    s = re.sub(r"^[*_`\s]+|[*_`\s]+$", "", s)
    s = re.sub(r"(?<![0-9])\.\s*$", "", s)
    s = s.strip()
    if re.fullmatch(r"[a-e]+", s):
        s = s.upper()
    if re.fullmatch(r"[A-Ea-e](?:[\s,，;；、和与]+[A-Ea-e])+\.?", s):
        letters = sorted({c.upper() for c in s if c.isalpha()})
        if letters and all(c in "ABCDE" for c in letters):
            s = "".join(letters)
    return s


def make_client(api_key: str | None, base_url: str | None):
    from openai import OpenAI
    return OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )


def chat(client, model, messages, max_tokens, temperature, timeout, max_retries=5):
    last_err = None
    for attempt in range(max_retries):
        try:
            r = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature, timeout=timeout,
            )
            text = r.choices[0].message.content or ""
            finish = getattr(r.choices[0], "finish_reason", None)
            usage = {}
            if r.usage:
                usage = {"prompt_tokens": r.usage.prompt_tokens,
                         "completion_tokens": r.usage.completion_tokens,
                         "total_tokens": r.usage.total_tokens}
            usage["finish_reason"] = finish
            return text, usage
        except Exception as e:
            last_err = e
            sleep = min(2 ** attempt, 30) + random.uniform(0, 1.5)
            sys.stderr.write(f"  [retry {attempt + 1}] {type(e).__name__}: {str(e)[:140]}; sleep {sleep:.1f}s\n")
            time.sleep(sleep)
    raise RuntimeError(f"chat failed after {max_retries} retries: {last_err}")


def juror_call(client, juror_model: str, row, max_tokens: int, timeout: float, max_retries: int):
    problem = row.get("problem") or ""
    images = get_images(row)
    content: list[dict] = [{"type": "text", "text": JUROR_USER.format(problem=problem)}]
    for im in images:
        u = to_data_url(im)
        if u:
            content.append({"type": "image_url", "image_url": {"url": u}})
    msg = [{"role": "system", "content": JUROR_SYSTEM},
           {"role": "user", "content": content}]
    text, usage = chat(client, juror_model, msg, max_tokens, 0.0, timeout, max_retries)
    answer, reasoning = parse_xml(text)
    return {
        "ok": True,
        "qid": row["question_id"],
        "level": row["__level__"],
        "model": juror_model,
        "answer": answer,
        "reasoning": (reasoning or "")[:3000],
        "raw": text[:6000],
        "usage": usage,
    }


def load_split(level: str, split: str) -> pd.DataFrame:
    f = DATA_DIR / level / f"{split}-00000-of-00001.parquet"
    df = pd.read_parquet(f)
    df["__level__"] = level
    df["__split__"] = split
    return df


def stage_run(args):
    run_dir = OUTPUT_DIR / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = run_dir / "jury" / args.juror.replace("/", "_")
    cache_dir.mkdir(parents=True, exist_ok=True)

    levels = ["level1", "level2", "level3", "level4", "level5"]
    splits: list[str] = []
    if args.split in ("testmini", "both"):
        splits.append("testmini")
    if args.split in ("test", "both"):
        splits.append("test")

    frames = []
    for lv in levels:
        for sp in splits:
            try:
                d = load_split(lv, sp)
                frames.append(d)
            except FileNotFoundError:
                pass
    df = pd.concat(frames, ignore_index=True)

    pending = []
    for _, row in df.iterrows():
        qid = row["question_id"]
        cache_path = cache_dir / f"{qid}.json"
        if cache_path.exists():
            try:
                j = json.loads(cache_path.read_text())
                if j.get("ok"):
                    continue
            except Exception:
                pass
        pending.append(row.to_dict())
    print(f"juror={args.juror}; split={args.split}; total={len(df)}; pending={len(pending)}")

    if args.dry_run or not pending:
        return

    client = make_client(args.api_key, args.base_url)
    completed = failed = 0
    t0 = time.time()
    stop = {"flag": False}

    def handle(signum, _f):
        sys.stderr.write(f"\n[signal {signum}] stopping...\n")
        stop["flag"] = True
    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    def runner(row):
        rec = juror_call(client, args.juror, row, args.max_tokens, args.timeout, args.max_retries)
        cache_path = cache_dir / f"{rec['qid']}.json"
        tmp = cache_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False))
        tmp.replace(cache_path)
        return rec

    failures_path = run_dir / f"jury_{args.juror.replace('/', '_')}_failures.jsonl"
    heartbeat_path = run_dir / f"jury_{args.juror.replace('/', '_')}_heartbeat.json"

    futures = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for row in pending:
            if stop["flag"]:
                break
            futures[ex.submit(runner, row)] = row["question_id"]

        for fut in as_completed(futures):
            qid = futures[fut]
            try:
                fut.result()
                completed += 1
            except Exception as e:
                failed += 1
                with failures_path.open("a") as fp:
                    fp.write(json.dumps({"qid": qid, "error": str(e), "trace": traceback.format_exc()[:1500]}) + "\n")
                sys.stderr.write(f"FAIL {qid}: {type(e).__name__}: {str(e)[:200]}\n")
            if (completed + failed) % 5 == 0 or (completed + failed) == len(pending):
                dt = time.time() - t0
                rate = (completed + failed) / max(dt, 1e-6)
                eta = (len(pending) - (completed + failed)) / max(rate, 1e-9)
                heartbeat_path.write_text(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "completed": completed, "failed": failed,
                    "pending_total": len(pending),
                    "rate_per_s": round(rate, 3),
                    "eta_minutes": round(eta / 60, 1),
                }, indent=2))
                print(f"  progress: ok={completed} fail={failed} rate={rate:.2f}/s eta={eta/60:.1f}m")

    print(f"DONE juror={args.juror}: ok={completed} fail={failed} elapsed={(time.time() - t0)/60:.1f}m")


def stage_aggregate(args):
    """Combine our prediction CSV with N juror predictions into a voted final CSV."""
    run_dir = OUTPUT_DIR / args.run_name
    our_csv = run_dir / args.our_csv

    # Load our answers
    our: dict[str, str] = {}
    our_reasoning: dict[str, str] = {}
    with open(our_csv) as f:
        for r in csv.DictReader(f):
            our[r["question_id"]] = r["prediction"]
            our_reasoning[r["question_id"]] = r["reasoning"]
    print(f"loaded {len(our)} rows from our prediction ({our_csv.name})")

    # Load each juror's answers
    juror_answers: dict[str, dict[str, str]] = {}
    for j in args.jurors:
        cache_dir = run_dir / "jury" / j.replace("/", "_")
        if not cache_dir.exists():
            print(f"  juror {j}: no cache dir, skipping")
            continue
        d: dict[str, str] = {}
        for f in cache_dir.glob("*.json"):
            try:
                rec = json.loads(f.read_text())
                if rec.get("ok"):
                    d[rec["qid"]] = rec.get("answer", "")
            except Exception:
                continue
        juror_answers[j] = d
        print(f"  juror {j}: {len(d)} answers")

    # Aggregate
    rows_out = []
    stats = Counter()
    for qid, our_ans in our.items():
        candidates: list[tuple[str, str]] = []
        candidates.append(("ours", our_ans))
        for j, d in juror_answers.items():
            if qid in d and d[qid].strip():
                candidates.append((j, d[qid]))

        # Normalize for voting
        normed = [(src, normalize_answer(a)) for src, a in candidates]
        votes = Counter(n for _, n in normed if n)
        if not votes:
            final = our_ans
            stats["empty_all"] += 1
        else:
            top, top_count = votes.most_common(1)[0]
            second_count = votes.most_common(2)[1][1] if len(votes) > 1 else 0
            our_norm = normalize_answer(our_ans)
            if top_count > second_count:
                # Strict majority
                if top == our_norm:
                    stats["majority_agrees_with_us"] += 1
                    final = our_ans
                else:
                    # Take the source that produced the winning answer (prefer ours if normalized matches)
                    src_for_top = next(s for s, n in normed if n == top)
                    final = next((a for s, a in candidates if s == src_for_top), our_ans)
                    stats["majority_overrules_us"] += 1
            else:
                # Tie — keep ours
                final = our_ans
                stats["tie_kept_ours"] += 1

        rows_out.append({
            "question_id": qid,
            "prediction": final,
            "reasoning": our_reasoning.get(qid, ""),
        })

    # Write voted CSV
    out_csv = run_dir / "prediction_voted.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["question_id", "prediction", "reasoning"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nwrote {out_csv}  ({len(rows_out)} rows)")

    # Build submission_voted.zip
    private_csv = run_dir / "prediction_private.csv"
    out_zip = run_dir / "submission_voted.zip"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_csv, arcname="prediction.csv")
        if private_csv.exists():
            z.write(private_csv, arcname="prediction_private.csv")
    print(f"wrote {out_zip}")

    print("\naggregation stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-name", default="v2_pub830")
    p.add_argument("--split", choices=["testmini", "test", "both"], default="testmini")
    sub = p.add_argument
    # run mode
    p.add_argument("--juror", help="single juror model id (e.g. gpt-5.5). required unless --aggregate")
    p.add_argument("--workers", type=int, default=30)
    p.add_argument("--max-tokens", type=int, default=131072)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--max-retries", type=int, default=5)
    p.add_argument("--api-key", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--dry-run", action="store_true")
    # aggregate mode
    p.add_argument("--aggregate", action="store_true")
    p.add_argument("--jurors", nargs="*", default=[])
    p.add_argument("--our-csv", default="prediction_audited.csv")
    return p.parse_args()


def main():
    args = parse_args()
    if args.aggregate:
        stage_aggregate(args)
    else:
        if not args.juror:
            sys.exit("--juror required (or pass --aggregate)")
        stage_run(args)


if __name__ == "__main__":
    main()
