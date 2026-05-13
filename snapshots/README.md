# Snapshots

One-off snapshots of audit outputs that are normally gitignored under `clients/<slug>/output/`. Useful for sharing a report via a GitHub link.

These files are **point-in-time** — they don't auto-update when the audit re-runs locally. To regenerate, run:

```bash
python audit.py --client <slug>
```

…then copy the output files here if you want the snapshot updated.

## Current snapshots

| Client | Date | Files |
|---|---|---|
| `wheelhouseit/` | 2026-05-13 | `action_list.md`, `action_list.csv`, `summary.md` |
