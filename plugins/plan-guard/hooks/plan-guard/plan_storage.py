"""Plan file storage, runtime-specific indexing, and recoverable archival."""
import datetime as dt
import fcntl
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from agent_runtime import agent_home, data_dir, runtime_name


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def atomic_write(path, text):
    fd, name = tempfile.mkstemp(prefix=".plan-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def archive_codex(age, dry_run=False):
    match = re.fullmatch(r"([1-9][0-9]*)([wdm])", age)
    if not match:
        raise ValueError("Age must be a positive number plus w, d, or m")
    days = int(match[1]) * {"w": 7, "d": 1, "m": 30}[match[2]]
    cutoff = time.time() - days * 86400
    index = data_dir("plan-guard") / "projects.json"
    projects = json.loads(index.read_text()) if index.exists() else []
    if not isinstance(projects, list):
        raise ValueError("Invalid project index")
    count = 0
    for project in projects:
        if not isinstance(project, str) or not Path(project).is_absolute():
            continue
        directory = Path(project) / ".Codex/plan-guard/plans"
        if not directory.is_dir() or any(x.is_symlink() for x in [Path(project), Path(project) / ".Codex", directory.parent, directory]):
            continue
        with locked(directory):
            for source in sorted(directory.glob("*.md")):
                if source.is_symlink() or not source.is_file() or source.stat().st_mtime >= cutoff:
                    continue
                destination_dir = directory / "archive" / dt.date.today().isoformat()
                if destination_dir.is_symlink() or destination_dir.parent.is_symlink():
                    raise ValueError("Refusing symlinked archive")
                if dry_run:
                    print(f"Would archive: {source}")
                    count += 1
                    continue
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = destination_dir / source.name
                suffix = 1
                while destination.exists() or destination.is_symlink():
                    destination = destination_dir / f"{source.stem}-{suffix}.md"
                    suffix += 1
                source.rename(destination)
                count += 1
                print(f"Archived: {source} -> {destination}")
    return count



def associations(plans):
    metadata = plans / ".metadata"
    if metadata.exists():
        return dict(line.rstrip("\n").split(":", 1) for line in metadata.read_text().splitlines() if ":" in line)
    legacy = plans.parent / "plan-projects.json"
    if legacy.exists():
        result = json.loads(legacy.read_text())
        if not isinstance(result, dict):
            raise ValueError("Invalid legacy plan metadata")
        return result
    return {}


def save_associations(plans, mapping):
    atomic_write(plans / ".metadata", "".join(f"{name}:{project}\n" for name, project in sorted(mapping.items())))


def archive_file(source):
    destination_dir = source.parent / "archive" / dt.date.today().isoformat()
    if destination_dir.is_symlink() or destination_dir.parent.is_symlink():
        raise ValueError("Refusing symlinked archive")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    suffix = 1
    while destination.exists() or destination.is_symlink():
        destination = destination_dir / f"{source.stem}-{suffix}.md"
        suffix += 1
    source.rename(destination)
    print(f"Archived: {source} -> {destination}")


def archive_claude(age, dry_run=False):
    match = re.fullmatch(r"([1-9][0-9]*)([wdm])", age)
    if not match:
        raise ValueError("Age must be a positive number plus w, d, or m")
    cutoff = time.time() - int(match[1]) * {"w": 7, "d": 1, "m": 30}[match[2]] * 86400
    home = agent_home()
    plans = home / "plans"
    count = 0
    if plans.is_symlink():
        raise ValueError("Refusing symlinked plans directory")
    if plans.is_dir():
        with locked(plans):
            mapping = associations(plans)
            for source in sorted(plans.glob("*.md")):
                if source.is_symlink() or not source.is_file() or source.stat().st_mtime >= cutoff:
                    continue
                associated = mapping.get(source.name)
                targets = [source]
                if associated:
                    if not isinstance(associated, str) or not Path(associated).is_absolute():
                        raise ValueError("Invalid project association")
                    project = Path(associated)
                    target = project / ".claude/plans" / source.name
                    if any(x.is_symlink() for x in [project, project / ".claude", target.parent, target]):
                        raise ValueError("Refusing symlinked project plan")
                    if target.is_file() and target.resolve() != source.resolve():
                        targets.append(target)
                if dry_run:
                    for target in targets:
                        print(f"Would archive: {target}")
                else:
                    # Project copy first: failure must not lose the global association.
                    for target in reversed(targets):
                        archive_file(target)
                    mapping.pop(source.name, None)
                count += 1
            if not dry_run:
                save_associations(plans, mapping)
    log = home / "logs/hook.log"
    if not dry_run and log.is_file() and not log.is_symlink():
        cutoff_date = dt.datetime.fromtimestamp(cutoff).date().isoformat()
        with locked(log.parent):
            lines = log.read_text().splitlines(keepends=True)
            retained = [line for line in lines if not re.match(r"^\d{4}-\d{2}-\d{2}", line) or line[:10] >= cutoff_date]
            atomic_write(log, "".join(retained))
    return count


def archive(age, dry_run=False):
    if runtime_name() == "codex":
        return archive_codex(age, dry_run)
    return archive_claude(age, dry_run)
