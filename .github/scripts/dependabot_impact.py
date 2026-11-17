import json
import os
import re
import urllib.parse
import urllib.request
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path.cwd()
MARKER = "<!-- dependabot-impact -->"
IGNORED = {".git", ".github", "node_modules", "_site", "data"}


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def workflows():
    return {p.name: p.read_text() for p in sorted((ROOT / ".github/workflows").glob("*.yml"))}


def declarations():
    found = {}
    for path in sorted(ROOT.glob("requirements*.txt")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            line = line.split("#")[0].strip()
            if line:
                found[norm(Requirement(line).name)] = f"{path.name}:{n}"
    return found


def dependents():
    graph = {}
    for dist in metadata.distributions():
        for raw in dist.requires or []:
            req = Requirement(raw)
            if not req.marker or req.marker.evaluate({"extra": ""}):
                graph.setdefault(norm(req.name), set()).add(norm(dist.metadata["Name"]))
    return graph


def chains(name, graph, declared):
    result, stack, seen = [], [[name]], {name}
    while stack:
        path = stack.pop()
        if path[-1] in declared and len(path) > 1:
            result.append(path[::-1])
        for parent in graph.get(path[-1], ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(path + [parent])
    return result


def modules_of(dists):
    return {m: norm(d) for m, ds in metadata.packages_distributions().items() for d in ds if norm(d) in dists}


def imports(modules):
    if not modules:
        return {}
    names = "|".join(map(re.escape, modules))
    pattern = re.compile(rf"^\s*(?:from|import)\s+({names})\b")
    found = {}
    for path in sorted(ROOT.rglob("*.py")):
        if IGNORED & set(path.relative_to(ROOT).parts):
            continue
        for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            m = pattern.match(line)
            if m:
                lines, mods = found.setdefault(path.relative_to(ROOT).as_posix(), ([], set()))
                lines.append(n)
                mods.add(m.group(1))
    return found


def runners(file, texts):
    name = Path(file).name
    if name in {"conftest.py", "site_config.py"}:
        return [wf for wf, t in texts.items() if "pytest" in t]
    return [wf for wf, t in texts.items() if re.search(rf"(?<![\w-]){re.escape(name)}\b", t)]


def advisories(ecosystem, name, version):
    eco = {"github_actions": "actions"}.get(ecosystem, ecosystem)
    query = {"ecosystem": eco, "affects": f"{name}@{version.lstrip('v')}" if version else name}
    request = urllib.request.Request(
        "https://api.github.com/advisories?" + urllib.parse.urlencode(query),
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {os.environ['GH_TOKEN']}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            data = json.load(resp)
    except Exception:
        return ["API des avis GitHub indisponible."]
    if not data:
        return [f"Aucun avis GHSA pour {name} {version}."]
    out = []
    for adv in data:
        fixes = {v["first_patched_version"] for v in adv["vulnerabilities"]
                 if v.get("first_patched_version") and norm(v["package"]["name"]) == norm(name)}
        fixed = f" Corrigé en {', '.join(sorted(fixes))}." if fixes else ""
        out.append(f"- [{adv['ghsa_id']}]({adv['html_url']}) ({adv['severity']}) : {adv['summary']}.{fixed}")
    return out


def pip_report(name, texts, declared, graph):
    name = norm(name)
    paths = chains(name, graph, declared)
    out = []
    if name in declared:
        out.append(f"Dépendance directe, déclarée dans `{declared[name]}`.")
    if paths:
        out.append("Tirée par : " + "; ".join(f"`{' > '.join(p)}` ({declared[p[0]]})" for p in paths) + ".")
    if not out:
        out.append("Ni déclarée ni installée par une dépendance déclarée.")

    involved = {name} | {d for p in paths for d in p}
    owners = modules_of(involved)
    found = imports(owners)
    if found:
        out += ["", "| Fichier | Lignes | Imports | Lancé par |", "|---|---|---|---|"]
        for file, (lines, mods) in found.items():
            mods_txt = ", ".join(f"`{m}`" if owners[m] in {name, norm(m)} else f"`{m}` (via {owners[m]})" for m in sorted(mods))
            run = ", ".join(f"`{w}`" for w in runners(file, texts)) or "aucun workflow"
            out.append(f"| `{file}` | {', '.join(map(str, lines))} | {mods_txt} | {run} |")
    plugins = sorted({norm(d.metadata["Name"]) for d in metadata.distributions()
                      if norm(d.metadata["Name"]) in involved and any(ep.group == "pytest11" for ep in d.entry_points)})
    for dist in plugins:
        wfs = ", ".join(f"`{w}`" for w in runners("tests/conftest.py", texts))
        out.append(f"\n`{dist}` est un plugin pytest, chargé par tous les tests ({wfs}).")
    if not found and not plugins:
        out.append("\nAucun import dans le code Python.")
    return out


def actions_report(name, texts):
    pattern = re.compile(rf"uses:\s*{re.escape(name)}@(\S+)")
    rows = []
    for wf, text in texts.items():
        job = "?"
        for n, line in enumerate(text.splitlines(), 1):
            if m := re.match(r"^  ([\w-]+):\s*$", line):
                job = m.group(1)
            if m := pattern.search(line):
                rows.append(f"| `{wf}` | {n} | `{job}` | `{m.group(1)}` |")
    if not rows:
        return ["Action absente des workflows."]
    return ["| Workflow | Ligne | Job | Version |", "|---|---|---|---|", *rows]


def main():
    deps = json.loads(os.environ["UPDATED_DEPS"])
    texts = workflows()
    declared = declarations()
    graph = dependents()
    out = [MARKER]
    for dep in deps:
        name, eco = dep["dependencyName"], dep["packageEcosystem"]
        out += ["", f"### {name} {dep.get('prevVersion')} vers {dep.get('newVersion')} ({eco})", ""]
        out += advisories(eco, name, dep.get("prevVersion"))
        out.append("")
        out += pip_report(name, texts, declared, graph) if eco == "pip" else actions_report(name, texts)
    print("\n".join(out))


if __name__ == "__main__":
    main()
