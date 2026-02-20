"""Planning Agent — generates implementation plans for GitHub issues."""

import json
import os
import urllib.request


def main():
    issue_title = os.environ.get("ISSUE_TITLE", "")
    issue_body = os.environ.get("ISSUE_BODY", "")

    with open("/tmp/repo_files.txt") as f:
        repo_structure = f.read()
    with open("/tmp/relevant_code.md") as f:
        relevant_code = f.read()[:40000]
    with open("/tmp/triage_comment.txt") as f:
        triage_analysis = f.read()

    prompt = f"""You are a principal software engineer creating an implementation plan for a GitHub issue in the NinjaStack monorepo — a schema-first agentic backend framework (Python, Google ADK, Pydantic, pytest).

## Issue
**Title:** {issue_title}
**Body:** {issue_body}

## Prior Triage Analysis
{triage_analysis}

## Repo Structure
{repo_structure}

## Relevant Source Code
{relevant_code}

## Your Task
Create a detailed, actionable implementation plan. Be specific about file paths, function signatures, and test cases.

Respond in this exact markdown format:

### 📋 Implementation Plan

#### Objective
(what this change accomplishes)

#### Approach
(high-level strategy — 2-3 sentences)

#### Changes

**1. `path/to/file.py`**
- What to change and why
- Specific functions/classes affected

**2. `path/to/another.py`**
- ...

#### New Files (if any)
- `path/to/new_file.py` — purpose

#### Test Plan
- [ ] Test case 1 — description
- [ ] Test case 2 — description
- Where tests should live: `libs/xxx/tests/test_xxx.py`

#### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All existing tests pass
- [ ] New tests added and passing

#### Risk Assessment
**Risk:** Low / Medium / High
**Breaking changes:** Yes / No
**Migration needed:** Yes / No
"""

    body = json.dumps({
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000,
        "temperature": 0.2,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    plan = result["choices"][0]["message"]["content"]

    with open("/tmp/plan.md", "w") as f:
        f.write(plan)

    print("Plan generated.")


if __name__ == "__main__":
    main()
