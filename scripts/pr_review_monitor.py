#!/usr/bin/env python3
"""Post PR review reminders for the local MCP-backed review workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Any

MARKER_PREFIX = "pr-review-reminder:head="


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    head_sha: str
    head_ref: str
    base_ref: str
    url: str
    draft: bool


def _gh_command() -> str:
    explicit = os.environ.get("GH_BIN")
    if explicit:
        return explicit

    for name in ("gh", "gh.exe"):
        path = shutil.which(name)
        if path:
            return path

    raise RuntimeError("gh CLI not found")


def _run_gh(args: list[str], *, input_text: str | None = None) -> str:
    command = [_gh_command(), *args]
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"gh {' '.join(args)} failed: {detail}")
    return result.stdout


def _api_json(path: str) -> Any:
    output = _run_gh(["api", path])
    if not output.strip():
        return None
    return json.loads(output)


def _detect_repo() -> str:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo

    output = _run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    repo = output.strip()
    if not repo:
        raise RuntimeError("--repo or GITHUB_REPOSITORY is required")
    return repo


def _to_pr(payload: dict[str, Any]) -> PullRequest:
    return PullRequest(
        number=int(payload["number"]),
        title=str(payload.get("title") or ""),
        head_sha=str(payload["head"]["sha"]),
        head_ref=str(payload["head"]["ref"]),
        base_ref=str(payload["base"]["ref"]),
        url=str(payload.get("html_url") or ""),
        draft=bool(payload.get("draft")),
    )


def _list_open_prs(repo: str) -> list[PullRequest]:
    prs: list[PullRequest] = []
    page = 1
    while True:
        payload = _api_json(f"repos/{repo}/pulls?state=open&per_page=100&page={page}")
        if not isinstance(payload, list):
            raise RuntimeError("GitHub pull request list response was not a list")

        prs.extend(_to_pr(item) for item in payload)
        if len(payload) < 100:
            return prs
        page += 1


def _get_pr(repo: str, number: int) -> PullRequest:
    payload = _api_json(f"repos/{repo}/pulls/{number}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"GitHub pull request #{number} response was not an object")
    return _to_pr(payload)


def _list_comment_bodies(repo: str, issue_number: int) -> list[str]:
    bodies: list[str] = []
    page = 1
    while True:
        payload = _api_json(
            f"repos/{repo}/issues/{issue_number}/comments?per_page=100&page={page}"
        )
        if not isinstance(payload, list):
            raise RuntimeError("GitHub issue comments response was not a list")

        bodies.extend(str(item.get("body") or "") for item in payload)
        if len(payload) < 100:
            return bodies
        page += 1


def _has_current_marker(repo: str, pr: PullRequest) -> bool:
    marker = f"{MARKER_PREFIX}{pr.head_sha}"
    return any(marker in body for body in _list_comment_bodies(repo, pr.number))


def _comment_body(pr: PullRequest) -> str:
    return textwrap.dedent(
        f"""
        ## MCP 기반 리뷰 필요

        이 저장소는 GitHub Actions에서 외부 LLM API key를 사용하지 않습니다. PR 리뷰는 로컬 agent가 `python-krtour-map`과 같은 MCP 진입 방식으로 수행합니다.

        필수 진입:
        - `.codex/config.toml`, `claude.json`, `antigravity.json`, `.gemini/mcp.json`의 MCP 설정 확인
        - CodeGraph: `codegraph sync` 후 변경 심볼은 `codegraph_explore` / `codegraph_impact` 우선
        - Playwright: UI 변경이면 WSL dev server + Windows browser runner로 확인
        - Sequential Thinking: 설계 경계가 흐린 PR이면 짧게 사고 기록
        - Telegram: PR 처리 완료 후 `mcp-telegram` `send_message`로 요약 + PR 링크 전송

        리뷰 기준:
        - `docs/runbooks/pr-review-sprint4.md` 기준으로 변경분만 리뷰
        - 차단 이슈, 필요한 코드 수정, 검증 결과, 머지 판단을 PR에 별도 코멘트로 기록
        - ADR / Sprint 목표 / TripMate와 `python-krtour-map` 책임 경계 위반 여부 확인

        대상:
        - PR: #{pr.number} `{pr.title}`
        - branch: `{pr.head_ref}` -> `{pr.base_ref}`
        - head: `{pr.head_sha}`

        <!-- {MARKER_PREFIX}{pr.head_sha} -->
        """
    ).strip()


def _post_comment(repo: str, pr: PullRequest) -> None:
    _run_gh(
        [
            "api",
            f"repos/{repo}/issues/{pr.number}/comments",
            "-X",
            "POST",
            "-f",
            f"body={_comment_body(pr)}",
        ]
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post missing PR review reminder comments for current PR heads."
    )
    parser.add_argument("--repo", help="GitHub repository, for example digitie/tripmate")
    parser.add_argument("--pr-number", type=int, help="Limit monitoring to one PR number")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Post even when the current head marker already exists",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Post reminders for draft PRs too",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo = args.repo or _detect_repo()
    prs = [_get_pr(repo, args.pr_number)] if args.pr_number else _list_open_prs(repo)

    posted = 0
    skipped = 0
    for pr in prs:
        if pr.draft and not args.include_drafts:
            print(f"skip draft PR #{pr.number}")
            skipped += 1
            continue

        if not args.force and _has_current_marker(repo, pr):
            print(f"skip PR #{pr.number}: marker already exists for {pr.head_sha}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"would post reminder for PR #{pr.number} at {pr.head_sha}")
        else:
            _post_comment(repo, pr)
            print(f"posted reminder for PR #{pr.number} at {pr.head_sha}")
        posted += 1

    print(f"done: posted={posted} skipped={skipped} checked={len(prs)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"pr_review_monitor failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
