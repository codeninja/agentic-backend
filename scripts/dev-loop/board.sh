#!/usr/bin/env bash
# =============================================================================
# Board helpers — thin wrappers around ninja-board CLI
# =============================================================================
# Uses $NINJA_BOARD set in config.sh

issues_by_status() {
    $NINJA_BOARD issues-by-status "$1" 2>/dev/null
}

count_status() {
    $NINJA_BOARD count-status "$1" 2>/dev/null
}

# set_status takes issue_number and STATUS NAME (not option ID)
# e.g., set_status 123 "Todo"
set_status() {
    local issue_num="$1" status_name="$2"
    $NINJA_BOARD set-status "$issue_num" "$status_name" 2>/dev/null
}

get_issue_context() {
    $NINJA_BOARD context "$1" 2>/dev/null
}

get_issue_title() {
    $NINJA_BOARD context "$1" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null
}

get_issue_body() {
    $NINJA_BOARD context "$1" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('body',''))" 2>/dev/null
}

get_prioritized_todo_issues() {
    $NINJA_BOARD prioritized-todo 2>/dev/null
}

invalidate_board_cache() {
    $NINJA_BOARD sync 2>/dev/null
}

get_item_id() {
    $NINJA_BOARD context "$1" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('item_id',''))" 2>/dev/null
}

get_pr_for_branch() {
    local branch="$1"
    gh pr list --repo "$REPO" --head "$branch" --json number -q '.[0].number' 2>/dev/null
}
