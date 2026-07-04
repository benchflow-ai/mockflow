#!/usr/bin/env python3
"""Evaluate gdoc-search-keyword-index task.

Scoring (0.0 to 1.0):
  - Index document created with correct title ("Budget Documents Index") -> +0.15
  - Each of 5 budget docs found and listed in index -> +0.12 each (x5 = 0.60)
  - No false positives (non-budget docs listed) -> +0.10
  - Each false positive listed -> -0.15 (up to -0.45 cap)
  - Used search API -> +0.05
  - Multiple search queries used -> +0.10
"""

import argparse
import json
import os


BUDGET_DOC_TITLES = [
    "Q1 Department Budget Proposal",
    "Project Phoenix Status Report",
    "Annual Planning Meeting Notes",
    "Vendor Evaluation Summary",
    "Facilities Operations Review",
]

DECOY_TITLES = [
    "Team Standup Notes",
    "API v2.0 Design Document",
    "Incident Postmortem",
    "Code Review Guidelines",
    "Onboarding Checklist",
    # Near-miss decoys (financial context, but no "budget" in content)
    "Q4 Revenue Forecast",
    "Compensation Review Process",
    "Office Lease Renewal Terms",
    "Q2 Cost Allocation Proposal",
]


def _word_count(text: str) -> int:
    return len([part for part in text.replace("-", " ").split() if part.strip()])


def _has_summary_for_title(text: str, title: str) -> bool:
    """Return True when a title has adjacent one-line summary text."""
    known_titles = {t.lower() for t in BUDGET_DOC_TITLES + DECOY_TITLES}
    title_lower = title.lower()
    lines = [line.strip() for line in text.splitlines()]

    for index, line in enumerate(lines):
        line_lower = line.lower()
        if title_lower not in line_lower:
            continue

        after_title = line_lower.split(title_lower, 1)[1].strip(" :-—–|")
        if _word_count(after_title) >= 4:
            return True

        for next_line in lines[index + 1:]:
            next_lower = next_line.lower()
            if not next_lower:
                continue
            if next_lower in known_titles:
                return False
            if any(next_lower.startswith(f"{known}:") for known in known_titles):
                return False
            return _word_count(next_line) >= 4
    return False


def _extract_text(body: dict) -> str:
    text_parts = []
    for element in body.get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for para_element in paragraph.get("elements", []):
            text_run = para_element.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def evaluate(final_state: dict, diff: dict, action_log: list) -> dict:
    metrics = {}
    reward = 0.0

    new_docs = []
    for user_data in diff.get("updated", {}).values():
        new_docs.extend(user_data.get("documents", {}).get("added", []))

    index_doc = None
    for doc in new_docs:
        title = doc.get("title", "").lower()
        if "budget" in title and "index" in title:
            index_doc = doc
            break

    metrics["index_doc_exists"] = index_doc is not None
    if index_doc:
        reward += 0.15

        body = index_doc.get("body", {})
        text = _extract_text(body)
        text_lower = text.lower()

        found_count = 0
        summarized_count = 0
        for title in BUDGET_DOC_TITLES:
            found = title.lower() in text_lower
            metrics[f"found_{title[:20].replace(' ', '_').lower()}"] = found
            if found:
                found_count += 1
                summarized = _has_summary_for_title(text, title)
                metrics[f"summarized_{title[:20].replace(' ', '_').lower()}"] = summarized
                if summarized:
                    summarized_count += 1
                    reward += 0.12

        metrics["budget_docs_found"] = found_count
        metrics["budget_docs_summarized"] = summarized_count
        metrics["budget_docs_total"] = len(BUDGET_DOC_TITLES)

        false_positives = 0
        for title in DECOY_TITLES:
            if title.lower() in text_lower:
                false_positives += 1
        metrics["false_positives"] = false_positives
        metrics["no_false_positives"] = false_positives == 0

        # Graduated FP penalty: each false positive costs -0.15, up to -0.45
        fp_penalty = min(false_positives * 0.15, 0.45)
        reward -= fp_penalty
        metrics["fp_penalty"] = round(fp_penalty, 2)

        if false_positives == 0 and found_count >= 1:
            reward += 0.10
    else:
        metrics["budget_docs_found"] = 0
        metrics["budget_docs_summarized"] = 0
        metrics["budget_docs_total"] = len(BUDGET_DOC_TITLES)
        metrics["false_positives"] = 0

    metrics["api_calls"] = len(action_log)

    # Check if agent used search API
    search_queries = [
        entry for entry in action_log
        if entry.get("method") == "GET" and "q=" in entry.get("path", "").lower()
    ]
    used_search = len(search_queries) > 0
    metrics["used_search"] = used_search
    if used_search:
        reward += 0.05

    # Bonus for multiple search queries — finding all 5 docs requires
    # more than a single "budget" search since some docs bury the keyword
    used_multiple_searches = len(search_queries) >= 2
    metrics["used_multiple_searches"] = used_multiple_searches
    if used_multiple_searches:
        reward += 0.10

    return {"reward": round(max(min(reward, 1.0), 0.0), 2), "done": True, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    final_state = json.loads(open(args.state).read())
    diff = json.loads(open(args.diff).read())
    action_log_data = json.loads(open(args.action_log).read())
    log_entries = action_log_data.get("entries", action_log_data)

    result = evaluate(final_state, diff, log_entries)

    output_dir = os.path.dirname(args.output)
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "reward.txt"), "w") as f:
        f.write(str(result["reward"]))

    flat_metrics = {k: (1 if v is True else 0 if v is False else v)
                    for k, v in result.get("metrics", {}).items()
                    if isinstance(v, (int, float, bool))}
    flat_metrics["reward"] = result["reward"]
    with open(os.path.join(output_dir, "reward.json"), "w") as f:
        json.dump(flat_metrics, f, indent=2)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
