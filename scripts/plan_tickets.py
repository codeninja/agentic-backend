#!/usr/bin/env python3
"""
Plan tickets on the NinjaStack project board (#4).

Fetches all tickets in a given source state (default: Planning),
verifies triage, posts an implementation plan comment, and moves to a target state (default: Todo).

Usage:
    python3 scripts/plan_tickets.py                          # Planning → Todo (all)
    python3 scripts/plan_tickets.py --from Triage --to Planning  # Triage → Planning
    python3 scripts/plan_tickets.py --dry-run                # Preview without changes
    python3 scripts/plan_tickets.py --issues 124 125 130     # Only specific issues
"""
import subprocess, json, sys, re, os, argparse

# Board constants
PROJECT_ID = "PVT_kwHNOkLOAT6Qtg"
FIELD_ID = "PVTSSF_lAHNOkLOAT6Qts4Pf31M"
STATUS_OPTIONS = {
    "Triage":       "f75ad846",
    "Planning":     "5860e624",
    "Todo":         "398c03ac",
    "In Progress":  "47fc9ee4",
    "AI Review":    "adaa04e0",
    "Rejected":     "656e3c6f",
    "Done":         "873d8d61",
    "Need Human":   "0296d477",
}
OWNER = "codeninja"
REPO = "ninja-stack"
REPO_ROOT = os.path.expanduser(f"~/{REPO}")


def gh(*args, input_text=None):
    r = subprocess.run(["gh"] + list(args), capture_output=True, text=True, input=input_text)
    if r.returncode != 0 and r.stderr:
        raise RuntimeError(f"gh error: {r.stderr.strip()}")
    return r.stdout.strip()


def fetch_board_tickets(status_name):
    """Fetch all open tickets in a given board status column."""
    cursor = None
    tickets = []
    while True:
        after = f', after:"{cursor}"' if cursor else ""
        q = (
            f'query {{ user(login:"{OWNER}") {{ projectV2(number:4) {{ items(first:100{after}) '
            f'{{ pageInfo {{ hasNextPage endCursor }} nodes {{ '
            f'fieldValueByName(name:"Status") {{ ... on ProjectV2ItemFieldSingleSelectValue {{ name }} }} '
            f'content {{ ... on Issue {{ number title state }} }} }} }} }} }} }}'
        )
        raw = gh("api", "graphql", "-f", f"query={q}")
        data = json.loads(raw)["data"]["user"]["projectV2"]["items"]
        for item in data["nodes"]:
            content = item.get("content", {})
            status = (item.get("fieldValueByName") or {}).get("name", "(none)")
            if status == status_name and content.get("number") and content.get("state") == "OPEN":
                tickets.append(content["number"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    tickets.sort()
    return tickets


def get_issue(num):
    raw = gh("issue", "view", str(num), "--json", "number,title,body,labels,state")
    return json.loads(raw)


def extract_affected_files(body):
    """Extract file paths and line references from issue body."""
    files = []
    lines_info = {}
    for line in body.split("\n"):
        matches = re.findall(r"[`]?([a-zA-Z][\w\-/]*\.(?:py|yaml|yml|html|js|ts|toml))[`]?", line)
        for f in matches:
            if "/" in f and f not in files:
                files.append(f)
                lm = re.findall(r"lines?\s+([\d,\s\-]+)", line, re.IGNORECASE)
                if lm:
                    lines_info[f] = lm[0]
    return files, lines_info


def extract_section(body, header):
    """Extract a markdown section by header name."""
    for h in [f"## {header}", f"### {header}"]:
        if h in body:
            start = body.index(h) + len(h)
            rest = body[start:]
            next_h = rest.find("\n## ")
            if next_h < 0:
                next_h = rest.find("\n### ")
            return rest[:next_h].strip() if next_h > 0 else rest.strip()
    return ""


def generate_plan(issue):
    """Generate an implementation plan based on issue content."""
    num = issue["number"]
    title = issue["title"]
    body = issue.get("body", "") or ""

    files, lines_info = extract_affected_files(body)
    is_bug = "bug" in title.lower() or any(
        l.get("name", "").lower() == "bug" for l in issue.get("labels", [])
    )
    is_enhancement = any(kw in title.lower() for kw in ("enhancement", "add ", "implement"))

    # Verify files exist in repo
    verified, missing = [], []
    for f in files:
        (verified if os.path.exists(os.path.join(REPO_ROOT, f)) else missing).append(f)

    lines = ["## Implementation Plan (Auto-generated)", ""]

    # --- Triage verification ---
    lines.append("### Triage Verification")
    if verified:
        lines.append(f"- ✅ Affected files verified: {', '.join(f'`{f}`' for f in verified)}")
    if missing:
        lines.append(f"- ⚠️ Files not found (may have been moved/renamed): {', '.join(f'`{f}`' for f in missing)}")
    if not files:
        lines.append("- ℹ️ No specific files listed — implementation will need to locate relevant code")
    lines.append("")

    # --- Steps ---
    lines.append("### Steps")
    step = 1
    if is_bug:
        lines.append(f"{step}. **Write a failing test** that reproduces the described bug")
        step += 1
        for f in verified:
            hint = f" (around lines {lines_info[f]})" if f in lines_info else ""
            lines.append(f"{step}. **Fix** `{f}`{hint}")
            step += 1
        if not verified and not missing:
            lines.append(f"{step}. **Locate and fix** the affected code")
            step += 1
        lines.append(f"{step}. **Verify** the failing test now passes")
        step += 1
        lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        lines.append(f"{step}. **Commit** with message: `fix: {title} (closes #{num})`")
    elif is_enhancement:
        lines.append(f"{step}. **Design** the interface/API surface")
        step += 1
        lines.append(f"{step}. **Implement** the feature")
        step += 1
        if verified:
            for f in verified:
                lines.append(f"   - Modify `{f}`")
        lines.append(f"{step + 1}. **Write tests** covering happy path and edge cases")
        step += 2
        lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        lines.append(f"{step}. **Commit** with message: `feat: {title} (closes #{num})`")
    else:
        lines.append(f"{step}. **Analyze** the affected code paths")
        step += 1
        lines.append(f"{step}. **Implement** the fix/feature")
        step += 1
        lines.append(f"{step}. **Write tests** covering the changes")
        step += 1
        lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        lines.append(f"{step}. **Commit** with message: `fix: {title} (closes #{num})`")
    lines.append("")

    # --- Implementation details ---
    lines.append("### Implementation Details")
    current = extract_section(body, "Current Behavior")
    if current:
        lines.append("**Current (broken):**")
        lines.append(current[:500] + ("..." if len(current) > 500 else ""))
        lines.append("")

    expected = extract_section(body, "Expected Behavior")
    if expected:
        lines.append("**Expected (fixed):**")
        lines.append(expected[:500] + ("..." if len(expected) > 500 else ""))
        lines.append("")

    ac = extract_section(body, "Acceptance Criteria")
    if ac:
        lines.append("### Acceptance Criteria (from ticket)")
        lines.append(ac[:800])
        lines.append("")

    # --- Testing ---
    lines.append("### Testing")
    lines.append("- All new code must have corresponding tests")
    lines.append("- Run `pytest` from repo root — zero failures required")
    lines.append("- Test file naming: `test_<module>_<feature>.py` in the relevant `tests/` directory")

    return "\n".join(lines)


def move_ticket(num, target_option_id):
    """Move an issue to a board status column."""
    node_id = gh(
        "api", "graphql", "-f",
        f'query=query($o:String!,$r:String!,$n:Int!){{repository(owner:$o,name:$r){{issue(number:$n){{id}}}}}}',
        "-F", f"o={OWNER}", "-F", f"r={REPO}", "-F", f"n={num}",
        "-q", ".data.repository.issue.id",
    )
    item_id = gh(
        "api", "graphql", "-f",
        f'query=mutation($p:ID!,$c:ID!){{addProjectV2ItemById(input:{{projectId:$p,contentId:$c}}){{item{{id}}}}}}',
        "-F", f"p={PROJECT_ID}", "-F", f"c={node_id}",
        "-q", ".data.addProjectV2ItemById.item.id",
    )
    gh(
        "api", "graphql", "-f",
        f'query=mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){{updateProjectV2ItemFieldValue(input:{{projectId:$p,itemId:$i,fieldId:$f,value:{{singleSelectOptionId:$v}}}}){{projectV2Item{{id}}}}}}',
        "-F", f"p={PROJECT_ID}", "-F", f"i={item_id}", "-F", f"f={FIELD_ID}", "-F", f"v={target_option_id}",
    )


def main():
    parser = argparse.ArgumentParser(description="Plan and promote NinjaStack board tickets")
    parser.add_argument("--from", dest="from_status", default="Planning", choices=STATUS_OPTIONS.keys(),
                        help="Source board column (default: Planning)")
    parser.add_argument("--to", dest="to_status", default="Todo", choices=STATUS_OPTIONS.keys(),
                        help="Target board column (default: Todo)")
    parser.add_argument("--issues", nargs="+", type=int, default=None,
                        help="Only process these issue numbers (skip board query)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan to stdout without posting or moving")
    parser.add_argument("--no-plan", action="store_true",
                        help="Move tickets without posting an implementation plan comment")
    args = parser.parse_args()

    target_id = STATUS_OPTIONS[args.to_status]

    # Fetch tickets
    if args.issues:
        tickets = sorted(args.issues)
        print(f"Processing {len(tickets)} specified issues → {args.to_status}")
    else:
        print(f"Fetching {args.from_status} tickets from board...", flush=True)
        tickets = fetch_board_tickets(args.from_status)
        print(f"Found {len(tickets)} tickets in {args.from_status}")

    if not tickets:
        print("Nothing to do.")
        return

    success, failed = 0, 0
    for idx, num in enumerate(tickets, 1):
        print(f"\n[{idx}/{len(tickets)}] #{num}...", end=" ", flush=True)
        try:
            issue = get_issue(num)
            if issue["state"] != "OPEN":
                print(f"⏭️ {issue['state']}")
                continue

            plan = generate_plan(issue)

            if args.dry_run:
                print(f"DRY RUN — {issue['title'][:60]}")
                print(plan)
                print("---")
            else:
                if not args.no_plan:
                    gh("issue", "comment", str(num), "--body", plan)
                    print("📝", end=" ", flush=True)
                move_ticket(num, target_id)
                print(f"✅ → {args.to_status}")
            success += 1
        except Exception as e:
            print(f"❌ {e}")
            failed += 1

    print(f"\nDone: {success} processed, {failed} failed")


if __name__ == "__main__":
    main()
