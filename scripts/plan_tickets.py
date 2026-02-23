#!/usr/bin/env python3
"""
Iterate over Planning tickets, verify triage, create implementation plan, move to Todo.
"""
import subprocess, json, sys, re, os

PROJECT_ID = "PVT_kwHNOkLOAT6Qtg"
FIELD_ID = "PVTSSF_lAHNOkLOAT6Qts4Pf31M"
TODO_ID = "398c03ac"

TICKETS = [124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,140,141,145,146,147,148,149,150,152,153,155,156,157,158,160,161,162,163,164,165,166,169,170,171,172,173,174,175,176,177,180,181,182,185,186,187,188,189,190,191,192,201,209,214,225,226,227,236]

def gh(*args, input_text=None):
    r = subprocess.run(['gh'] + list(args), capture_output=True, text=True, input=input_text)
    return r.stdout.strip()

def get_issue(num):
    raw = gh('issue', 'view', str(num), '--json', 'number,title,body,labels,state')
    return json.loads(raw)

def get_file_snippet(filepath, lines=None):
    """Try to read relevant lines from repo to verify the bug exists."""
    try:
        if lines:
            # Parse line range
            m = re.search(r'(\d+)', str(lines))
            if m:
                start = max(1, int(m.group(1)) - 2)
                end = start + 15
                r = subprocess.run(['sed', '-n', f'{start},{end}p', filepath], 
                                   capture_output=True, text=True, cwd=os.path.expanduser('~/ninja-stack'))
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
        r = subprocess.run(['head', '-30', filepath], capture_output=True, text=True, 
                           cwd=os.path.expanduser('~/ninja-stack'))
        if r.returncode == 0:
            return r.stdout.strip()
    except:
        pass
    return None

def extract_affected_files(body):
    """Extract file paths from issue body."""
    files = []
    lines_info = {}
    for line in body.split('\n'):
        # Match paths like libs/foo/src/bar.py or apps/foo/src/bar.py
        m = re.findall(r'[`]?([a-zA-Z][\w\-/]*\.(?:py|yaml|yml|html|js|ts|toml))[`]?', line)
        for f in m:
            if '/' in f and f not in files:
                files.append(f)
                # Check for line numbers
                lm = re.findall(r'line[s]?\s+([\d,\s\-]+)', line, re.IGNORECASE)
                if lm:
                    lines_info[f] = lm[0]
    return files, lines_info

def generate_plan(issue):
    """Generate implementation plan based on issue content."""
    num = issue['number']
    title = issue['title']
    body = issue.get('body', '') or ''
    
    files, lines_info = extract_affected_files(body)
    
    # Determine issue type
    is_bug = 'bug' in title.lower() or any(l.get('name','').lower() == 'bug' for l in issue.get('labels', []))
    is_enhancement = 'enhancement' in title.lower() or 'add ' in title.lower() or 'implement' in title.lower()
    
    # Extract acceptance criteria
    ac_section = ''
    if '## Acceptance Criteria' in body or '## Expected' in body:
        for header in ['## Acceptance Criteria', '## Expected Behavior', '## Expected']:
            if header in body:
                start = body.index(header)
                # Find next ## or end
                rest = body[start + len(header):]
                next_h = rest.find('\n## ')
                if next_h > 0:
                    ac_section = rest[:next_h].strip()
                else:
                    ac_section = rest.strip()
                break
    
    # Verify files exist
    verified_files = []
    missing_files = []
    for f in files:
        full = os.path.join(os.path.expanduser('~/ninja-stack'), f)
        if os.path.exists(full):
            verified_files.append(f)
        else:
            missing_files.append(f)
    
    # Build plan
    plan_lines = [f"## Implementation Plan (Auto-generated)"]
    plan_lines.append("")
    plan_lines.append(f"### Triage Verification")
    
    if verified_files:
        plan_lines.append(f"- ✅ Affected files verified: {', '.join(f'`{f}`' for f in verified_files)}")
    if missing_files:
        plan_lines.append(f"- ⚠️ Files not found (may have been moved/renamed): {', '.join(f'`{f}`' for f in missing_files)}")
    if not files:
        plan_lines.append("- ℹ️ No specific files listed in ticket — implementation will need to locate relevant code")
    
    plan_lines.append("")
    plan_lines.append("### Steps")
    
    if is_bug:
        step = 1
        plan_lines.append(f"{step}. **Write a failing test** that reproduces the described bug behavior")
        step += 1
        for f in verified_files:
            line_hint = f" (around lines {lines_info[f]})" if f in lines_info else ""
            plan_lines.append(f"{step}. **Fix** `{f}`{line_hint}")
            step += 1
        if not verified_files and not missing_files:
            plan_lines.append(f"{step}. **Locate and fix** the affected code")
            step += 1
        plan_lines.append(f"{step}. **Verify** the failing test now passes")
        step += 1
        plan_lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        plan_lines.append(f"{step}. **Commit** with message: `fix: {title} (closes #{num})`")
    elif is_enhancement:
        step = 1
        plan_lines.append(f"{step}. **Design** the interface/API surface")
        step += 1
        plan_lines.append(f"{step}. **Implement** the feature")
        step += 1
        for f in verified_files:
            plan_lines.append(f"   - Modify `{f}`")
        plan_lines.append(f"{step+1}. **Write tests** covering happy path and edge cases")
        step += 2
        plan_lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        plan_lines.append(f"{step}. **Commit** with message: `feat: {title} (closes #{num})`")
    else:
        step = 1
        plan_lines.append(f"{step}. **Analyze** the affected code paths")
        step += 1
        plan_lines.append(f"{step}. **Implement** the fix/feature")
        step += 1
        plan_lines.append(f"{step}. **Write tests** covering the changes")
        step += 1
        plan_lines.append(f"{step}. **Run full test suite** (`pytest`) — all tests must pass")
        step += 1
        plan_lines.append(f"{step}. **Commit** with message: `fix: {title} (closes #{num})`")
    
    # Add specific implementation guidance based on body content
    plan_lines.append("")
    plan_lines.append("### Implementation Details")
    
    # Parse current vs expected behavior
    if '## Current Behavior' in body:
        start = body.index('## Current Behavior')
        rest = body[start:]
        next_h = rest.find('\n## ', 3)
        if next_h > 0:
            current = rest[:next_h].replace('## Current Behavior', '').strip()
        else:
            current = rest.replace('## Current Behavior', '').strip()
        # Trim to reasonable size
        if len(current) > 500:
            current = current[:500] + '...'
        plan_lines.append(f"**Current (broken):**")
        plan_lines.append(current)
        plan_lines.append("")
    
    if '## Expected Behavior' in body:
        start = body.index('## Expected Behavior')
        rest = body[start:]
        next_h = rest.find('\n## ', 3)
        if next_h > 0:
            expected = rest[:next_h].replace('## Expected Behavior', '').strip()
        else:
            expected = rest.replace('## Expected Behavior', '').strip()
        if len(expected) > 500:
            expected = expected[:500] + '...'
        plan_lines.append(f"**Expected (fixed):**")
        plan_lines.append(expected)
        plan_lines.append("")
    
    if ac_section:
        plan_lines.append("### Acceptance Criteria (from ticket)")
        plan_lines.append(ac_section[:800])
        plan_lines.append("")
    
    # Testing guidance
    plan_lines.append("### Testing")
    plan_lines.append("- All new code must have corresponding tests")
    plan_lines.append("- Run `pytest` from repo root — zero failures required")
    plan_lines.append("- Test file naming: `test_<module>_<feature>.py` in the relevant `tests/` directory")
    
    return '\n'.join(plan_lines)

def move_to_todo(num):
    """Move issue to Todo on project board."""
    # Get item ID
    node_id = gh('api', 'graphql', '-f', 
                 f'query=query($o:String!,$r:String!,$n:Int!){{repository(owner:$o,name:$r){{issue(number:$n){{id}}}}}}',
                 '-F', 'o=codeninja', '-F', 'r=ninja-stack', '-F', f'n={num}',
                 '-q', '.data.repository.issue.id')
    
    item_id = gh('api', 'graphql', '-f',
                 f'query=mutation($p:ID!,$c:ID!){{addProjectV2ItemById(input:{{projectId:$p,contentId:$c}}){{item{{id}}}}}}',
                 '-F', f'p={PROJECT_ID}', '-F', f'c={node_id}',
                 '-q', '.data.addProjectV2ItemById.item.id')
    
    gh('api', 'graphql', '-f',
       f'query=mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){{updateProjectV2ItemFieldValue(input:{{projectId:$p,itemId:$i,fieldId:$f,value:{{singleSelectOptionId:$v}}}}){{projectV2Item{{id}}}}}}',
       '-F', f'p={PROJECT_ID}', '-F', f'i={item_id}', '-F', f'f={FIELD_ID}', '-F', f'v={TODO_ID}')

def main():
    total = len(TICKETS)
    for idx, num in enumerate(TICKETS, 1):
        print(f"\n[{idx}/{total}] Processing #{num}...", flush=True)
        
        try:
            issue = get_issue(num)
            if issue['state'] != 'OPEN':
                print(f"  ⏭️ #{num} is {issue['state']}, skipping")
                continue
            
            plan = generate_plan(issue)
            
            # Post the plan as a comment
            gh('issue', 'comment', str(num), '--body', plan)
            print(f"  📝 Plan posted", flush=True)
            
            # Move to Todo
            move_to_todo(num)
            print(f"  ✅ #{num} → Todo", flush=True)
            
        except Exception as e:
            print(f"  ❌ Error on #{num}: {e}", flush=True)

if __name__ == '__main__':
    main()
