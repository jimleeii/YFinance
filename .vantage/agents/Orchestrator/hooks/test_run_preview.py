"""Quick preview runner for `hooks.log_hooks`.

Runs two preview calls (compact and full) so the log CLI is invoked with
`--preview` and no files are written. Useful for verification.
"""
from hooks.log_hooks import log_cycle


def main() -> None:
    print("== Preview: compact (single-agent) ==")
    res = log_cycle(
        "single-agent",
        event_flags={},
        summary="Preview compact entry",
        skills=["alpha", "beta"],
        preview=True,
    )
    print(res)

    print("\n== Preview: full (multi-agent + failure) ==")
    res2 = log_cycle(
        "multi-agent",
        event_flags={"failure_detected": True},
        summary="Preview full entry",
        skills=["alpha", "beta"],
        metadata={
            "curated_log": True,
            "project_request": "Preview full entry",
            "change_applied": "Render a curated full-log preview with concrete IDs.",
            "observed_result": "Preview mode should omit unresolved placeholder fields.",
            "decision": "keep",
        },
        transcript="Sample transcript text for preview",
        preview=True,
    )
    print(res2)


if __name__ == "__main__":
    main()
