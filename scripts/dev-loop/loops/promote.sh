#!/usr/bin/env bash
# =============================================================================
# Promote loop — move completed In Progress items to AI Review
# =============================================================================

loop_promote() {
    while check_loop_stop; do
        wait_for_rate_limit "promote" || return
        local in_progress_issues
        in_progress_issues=$(issues_by_status "In Progress")

        if [[ -n "$in_progress_issues" ]]; then
            while IFS= read -r issue_num; do
                [[ -z "$issue_num" ]] && continue

                # Check PR status from cached context
                local ctx pr_draft
                ctx=$(get_issue_context "$issue_num")
                pr_draft=$(echo "$ctx" | python3 -c "
import json, sys
d = json.load(sys.stdin)
pr = d.get('pull_request')
if pr:
    print('true' if pr.get('is_draft') else 'false')
else:
    print('none')
" 2>/dev/null)

                if [[ "$pr_draft" == "false" ]]; then
                    log "[promote] 📤 #$issue_num ready → AI Review"
                    set_status "$issue_num" "AI Review"
                fi
            done <<< "$in_progress_issues"
        fi

        sleep 90
    done
}
