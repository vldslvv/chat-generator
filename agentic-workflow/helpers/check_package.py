"""Validate the copied package and local Markdown links before use.

No arguments checks only the package containing this helper. --integration-root
PATH also checks PATH/AGENTS.md's marked workflow block and installed optional
workflow skills; ignores other host instructions/skills.

Read-only; creates no files and starts no capture or services.

Prints JSON with status (PASS/FAIL), errors and local_links_checked. Exit 0:
checks pass; 1: validation errors; 2: invalid arguments or check could not
complete (error on stderr).

Example: python3 agentic-workflow/helpers/check_package.py --integration-root .
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote


PACKAGE = Path(__file__).resolve().parents[1]
ROLES = ("SUPERVISOR", "PLANNER", "IMPLEMENTER", "REVIEWER", "VALIDATOR")
SKILLS = ("planner", "supervisor", "acceptance")


def anchors(text):
    # GitHub-style ATX heading anchors, including duplicate headings.
    used, result = {}, set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = used.get(slug, 0)
        result.add(f"{slug}-{count}" if count else slug)
        used[slug] = count + 1
    return result


def local_targets(text):
    # Installation examples inside fenced code are not links in this document.
    text = re.sub(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", "", text, flags=re.M | re.S)
    return [target for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
            if not re.match(r"[\w+.-]+:", target)]


def check_links(documents, boundary):
    errors, links = [], 0
    for source, text in documents.items():
        for target in local_targets(text):
            links += 1
            path, _, fragment = unquote(target).partition("#")
            destination = (source.parent / path if path else source).resolve()
            if not destination.is_relative_to(boundary.resolve()):
                errors.append(f"Link outside copy boundary in {source.name}: {target}")
            elif not destination.is_file():
                errors.append(f"Broken link in {source.name}: {target}")
            elif fragment and fragment not in anchors(destination.read_text()):
                errors.append(f"Missing anchor in {source.name}: {target}")
    return errors, links


def check(files):
    expected = {"README.md", "AGENTS.md", "WORKFLOW.md"}
    expected.update(f"roles/{role}.md" for role in ROLES)
    expected.update(f"policies/{name}.md" for name in
                    ("BUNDLE", "CHECKS", "DOCUMENT_STYLE", "GUIDELINES", "MEMORY", "MODELS",
                     "RECORDS", "RECONSTRUCTION"))
    expected.update(f"guides/{name}.md" for name in ("WORKFLOW_REVIEW", "TRACING"))
    expected.update(f"templates/{name}.md" for name in
                    ("project", "task_order", "tasks/task", "verification", "plan", "acceptance", "result"))
    expected.update(f"helpers/{name}.py" for name in
                    ("check_package", "records", "native_traces", "opencode_capture", "opencode_v2", "trace_adapters",
                     "usage_report", "trace_dashboard", "trace_view"))
    errors = [f"Missing package file: {p}" for p in sorted(expected - files.keys())]
    documents = {PACKAGE / name: data.decode() for name, data in files.items() if name.endswith(".md")}
    link_errors, links = check_links(documents, PACKAGE)
    errors.extend(link_errors)
    shared = files.get("AGENTS.md", b"").decode()
    for role in ROLES:
        if f"](roles/{role}.md)" not in shared:
            errors.append(f"Missing shared role entry point: {role}")
        if "](../AGENTS.md)" not in files.get(f"roles/{role}.md", b"").decode():
            errors.append(f"Missing shared-rules entry point in {role}")
    return errors, links


def check_integration(root):
    root = root.resolve()
    errors, documents = [], {}
    instructions = root / "AGENTS.md"
    text = instructions.read_text() if instructions.is_file() else ""
    start, end = "<!-- agentic-workflow:start -->", "<!-- agentic-workflow:end -->"
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        errors.append("Missing or invalid Agentic Workflow block in root AGENTS.md")
    else:
        block = text.split(start, 1)[1].split(end, 1)[0]
        documents[instructions] = block
        for path in ("AGENTS.md", "policies/DOCUMENT_STYLE.md", "policies/GUIDELINES.md",
                     "policies/MEMORY.md"):
            if f"agentic-workflow/{path}" not in local_targets(block):
                errors.append(f"Missing root entry point: {Path(path).stem}")
    for skill in SKILLS:
        name = f"agentic-workflow-{skill}"
        directory = root / ".agents/skills" / name
        if not directory.exists():
            continue
        source = directory / "SKILL.md"
        policy = directory / "agents/openai.yaml"
        content = source.read_text() if source.is_file() else ""
        invocation = policy.read_text() if policy.is_file() else ""
        required = (f"name: {name}", "description:", "disable-model-invocation: true")
        targets = local_targets(content)
        references = (["AGENTS.md", "roles/PLANNER.md", "roles/SUPERVISOR.md"]
                      if skill == "acceptance" else ["AGENTS.md", f"roles/{skill.upper()}.md"])
        if (not all(item in content for item in required)
                or not all(f"../../../agentic-workflow/{ref}" in targets for ref in references)):
            errors.append(f"Invalid skill entry point: {name}")
        if "allow_implicit_invocation: false" not in invocation or f"${name}" not in invocation:
            errors.append(f"Invalid invocation policy: {name}")
        documents[source] = content
    link_errors, links = check_links(documents, root)
    return errors + link_errors, links


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--integration-root", type=Path,
                        help="Also check the marked root AGENTS.md block and installed optional skills")
    args = parser.parse_args()
    try:
        current = {str(p.relative_to(PACKAGE)): p.read_bytes() for p in PACKAGE.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        errors, links = check(current)
        if args.integration_root is not None:
            integration_errors, integration_links = check_integration(args.integration_root)
            errors.extend(integration_errors)
            links += integration_links
        print(json.dumps({"status": "FAIL" if errors else "PASS",
                          "errors": errors, "local_links_checked": links}, indent=2))
        return 1 if errors else 0
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Package check could not complete: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
