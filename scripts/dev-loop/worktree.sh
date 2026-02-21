#!/usr/bin/env bash
# =============================================================================
# Git worktree helpers
# =============================================================================

create_implement_worktree() {
    local issue_num="$1" branch="$2" worktree="$3"
    (
        cd "$PROJECT_ROOT"
        git fetch origin main 2>/dev/null
        if git worktree add -b "$branch" "$worktree" origin/main 2>/dev/null; then
            :
        else
            git worktree add "$worktree" "$branch" 2>/dev/null
            cd "$worktree"
            git rebase origin/main 2>/dev/null || git rebase --abort 2>/dev/null
        fi
    )
    (
        cd "$worktree"
        git commit --allow-empty -m "wip: starting work on #$issue_num" 2>/dev/null
        git push -u origin "$branch" --force-with-lease 2>/dev/null
        gh pr create --repo "$REPO" --head "$branch" --base main \
            --title "fix: $(get_issue_title "$issue_num")" \
            --body "Closes #$issue_num" \
            --draft 2>/dev/null
    )
}

create_review_worktree() {
    local issue_num="$1" branch="$2" review_dir="$3"
    (
        cd "$PROJECT_ROOT"
        git fetch origin "$branch" main 2>/dev/null
        rm -rf "$review_dir" 2>/dev/null
        git worktree remove "$review_dir" 2>/dev/null || true
        git worktree add "$review_dir" "origin/$branch" 2>/dev/null || true
        cd "$review_dir"
        git checkout -b "review-${issue_num}" 2>/dev/null || true
        git rebase origin/main 2>/dev/null || git rebase --abort 2>/dev/null
    )
}

cleanup_worktree() {
    local worktree_path="$1"
    (cd "$PROJECT_ROOT" && git worktree remove "$worktree_path" 2>/dev/null || true)
}
