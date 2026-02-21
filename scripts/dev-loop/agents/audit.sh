#!/usr/bin/env bash
# =============================================================================
# Audit agent — spawn gap analysis when pipeline is low
# =============================================================================

loop_audit() {
    while check_loop_stop; do
        wait_for_rate_limit "audit" || return
        local active
        active=$(count_active_agents "audit")
        if (( active >= MAX_AUDIT_AGENTS )); then
            sleep 300; continue
        fi

        # Only audit when the triage queue is empty — no point creating work when there's plenty
        local triage_count todo_count planning_count pipeline_count
        triage_count=$(count_status "Triage")
        todo_count=$(count_status "Todo")
        planning_count=$(count_status "Planning")
        pipeline_count=$(( triage_count + todo_count + planning_count ))

        # Skip if board data hasn't loaded yet (all zeros = likely stale)
        if (( pipeline_count == 0 )); then
            local board_check
            board_check=$($NINJA_BOARD count-status "Done" 2>/dev/null)
            if [[ -z "$board_check" || "$board_check" == "0" ]]; then
                sleep 300; continue
            fi
        fi

        if (( triage_count == 0 && pipeline_count <= MIN_TODO_FOR_AUDIT )); then
            log "[audit] 🔍 Triage empty, pipeline=$pipeline_count (≤$MIN_TODO_FOR_AUDIT) — spawning audit agent"
            local audit_log="$LOG_DIR/audit-$(date +%s).log"

            # Build board context snapshot — titles of active/upcoming tickets (0 API calls)
            local board_context=""
            for _status in "Triage" "Planning" "Todo" "In Progress"; do
                local _nums _titles=""
                _nums=$(issues_by_status "$_status")
                if [[ -n "$_nums" ]]; then
                    while IFS= read -r _num; do
                        [[ -z "$_num" ]] && continue
                        local _title
                        _title=$(get_issue_title "$_num")
                        _titles+="  #${_num}: ${_title}"$'\n'
                    done <<< "$_nums"
                fi
                if [[ -n "$_titles" ]]; then
                    board_context+="${_status}:"$'\n'"${_titles}"
                else
                    board_context+="${_status}: (none)"$'\n'
                fi
            done

            claude --dangerously-skip-permissions -p "You are auditing the NinjaStack project for gaps, bugs, and security issues.

PROJECT ROOT: $PROJECT_ROOT
REPO: $REPO

## CURRENT BOARD STATE
The following tickets are already tracked. Do NOT create duplicates or overlapping issues.

$board_context


## Your task:
1. Read CLAUDE.md to understand the project architecture
2. Read implementation plans in docs/ and implementation_plans/
3. Examine source code in libs/ and apps/
4. Cross-reference the board state above — skip anything already covered by an existing ticket
5. Identify: security vulnerabilities, logic flaws, missing implementations, broken integrations
6. For EACH issue found:
   Step A — Create the issue:
     gh issue create --repo $REPO --title '<title>' --label 'bug' --label 'triage' --label 'priority: <high|medium|low>' --body '<detailed body>'
     NEVER use 'priority: critical' — reserved for humans.
     ALWAYS include '--label triage'.
   Step B — Add to project board:
     ITEM_ID=\$(gh project item-add $PROJECT_NUM --owner $PROJECT_OWNER --url <issue_url> --format json | jq -r '.id')
   Step C — Set board status:
     For bugs → Triage ($STATUS_TRIAGE):
       gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\", itemId: \"'\"\$ITEM_ID\"'\", fieldId: \"$FIELD_ID\", value: { singleSelectOptionId: \"$STATUS_TRIAGE\" } }) { projectV2Item { id } } }'
     For features → Planning ($STATUS_PLANNING):
       gh api graphql -f query='mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\", itemId: \"'\"\$ITEM_ID\"'\", fieldId: \"$FIELD_ID\", value: { singleSelectOptionId: \"$STATUS_PLANNING\" } }) { projectV2Item { id } } }'

## ORGANIZATION:
- Group related issues under Epics (label 'epic')
- Each issue references parent Epic: 'Part of #<epic_number>'
- Use 'enhancement' for features, 'bug' for defects
- NEVER 'priority: critical'

Do NOT create issues for things already tracked." \
                --output-format text \
                > "$audit_log" 2>&1 &
            track_agent_pid "audit" $!
            log "[audit] 🤖 Audit agent started (PID $!, log: $audit_log)"
        fi

        sleep 300
    done
}
