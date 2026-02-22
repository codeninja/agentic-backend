"""Triage Agent — analyzes GitHub issues against the codebase."""

import json
import os
import sys
import urllib.request


def main():
    issue_title = os.environ.get("ISSUE_TITLE", "")
    issue_body = os.environ.get("ISSUE_BODY", "")
    labels = os.environ.get("ISSUE_LABELS", "")

    with open("/tmp/context.md") as f:
        repo_structure = f.read()
    with open("/tmp/relevant_code.md") as f:
        relevant_code = f.read()[:30000]
    with open("/tmp/test_output.txt") as f:
        test_output = f.read()

    is_bug = "bug" in labels.lower()

    task = (
        "This is a BUG report. Identify the likely root cause, affected files,"
        " and whether existing tests cover this area."
        if is_bug
        else "This is a FEATURE/ENHANCEMENT request. Assess feasibility,"
        " identify affected components, and flag any architectural conflicts."
    )

    rc_or_feasibility = "Root Cause" if is_bug else "Feasibility Assessment"

    triage_intro = (
        "You are a senior software engineer triaging a GitHub issue"
        " for the NinjaStack monorepo"
        " — a schema-first agentic backend framework."
    )
    prompt = f"""{triage_intro}

## Issue
**Title:** {issue_title}
**Body:** {issue_body}
**Labels:** {labels}

## Repo Structure
{repo_structure}

## Relevant Code
{relevant_code}

## Test Results
{test_output}

## Your Task
{task}

Respond in this exact markdown format:

### 🔍 Triage Analysis

**Type:** Bug / Feature / Question / Invalid
**Confidence:** High / Medium / Low
**Recommendation:** `planning` or `wontfix`

#### Summary
(1-2 sentence summary of your findings)

#### {rc_or_feasibility}
(detailed analysis)

#### Affected Files
- `path/to/file.py` — reason

#### Test Coverage
(are there existing tests? what gaps exist?)

#### Suggested Approach
(brief implementation direction if recommending `planning`)
"""

    body = json.dumps(
        {
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": 2000,
            "temperature": 0.2,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
    except urllib.request.HTTPError as e:
        error_body = e.read().decode()
        print(f"OpenAI API error {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)
    result = json.loads(resp.read())
    analysis = result["choices"][0]["message"]["content"]

    with open("/tmp/analysis.md", "w") as f:
        f.write(analysis)

    print("Analysis complete.")


if __name__ == "__main__":
    main()
