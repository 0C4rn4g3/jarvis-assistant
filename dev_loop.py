"""Autonomous Self-Healing Compile and Test Loop.
Detects Maven, Gradle, or Python build tools.
Executes compilation/build, captures errors, parses stack traces,
and autonomously iterates up to 3 times to heal and patch code until build passes.
"""
import glob
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def detect_build_system(project_dir: str) -> str:
    """Detects whether directory uses maven, gradle, or python."""
    if os.path.exists(os.path.join(project_dir, "pom.xml")):
        return "maven"
    if os.path.exists(os.path.join(project_dir, "gradlew.bat")) or os.path.exists(os.path.join(project_dir, "build.gradle")) or os.path.exists(os.path.join(project_dir, "build.gradle.kts")):
        return "gradle"
    if os.path.exists(os.path.join(project_dir, "pyproject.toml")) or os.path.exists(os.path.join(project_dir, "requirements.txt")) or glob.glob(os.path.join(project_dir, "test_*.py")):
        return "python"
    return "unknown"


def parse_java_errors(output: str) -> List[Dict[str, Any]]:
    """Extracts Java compiler error lines from Maven/Gradle output."""
    errors = []
    # Pattern: [ERROR] /path/to/File.java:[line,col] error: message
    pattern = re.compile(r"\[ERROR\]\s+([A-Za-z]:\\[^:\n\r]+|\/[^:\n\r]+):\[(\d+),(\d+)\]\s+(?:error:\s*)?(.*)")
    for match in pattern.finditer(output):
        errors.append({
            "file": match.group(1).strip(),
            "line": int(match.group(2)),
            "col": int(match.group(3)),
            "message": match.group(4).strip(),
        })

    # Fallback pattern: File.java:line: error: message
    if not errors:
        fb_pattern = re.compile(r"([A-Za-z]:\\[^:\n\r]+\.java|\/[^:\n\r]+\.java):(\d+):\s+(?:error:\s*)?(.*)")
        for match in fb_pattern.finditer(output):
            errors.append({
                "file": match.group(1).strip(),
                "line": int(match.group(2)),
                "col": 0,
                "message": match.group(3).strip(),
            })
    return errors


def find_artifact(project_dir: str, build_tool: str) -> Optional[str]:
    """Finds compiled jar or build output."""
    if build_tool == "maven":
        target = os.path.join(project_dir, "target")
        if os.path.isdir(target):
            jars = [f for f in glob.glob(os.path.join(target, "*.jar")) if not f.endswith("-sources.jar") and not f.endswith("-javadoc.jar")]
            if jars:
                jars.sort(key=os.path.getmtime, reverse=True)
                return jars[0]
    elif build_tool == "gradle":
        libs = os.path.join(project_dir, "build", "libs")
        if os.path.isdir(libs):
            jars = [f for f in glob.glob(os.path.join(libs, "*.jar")) if not f.endswith("-sources.jar")]
            if jars:
                jars.sort(key=os.path.getmtime, reverse=True)
                return jars[0]
    return None


def execute_build(project_dir: str, build_tool: str) -> Dict[str, Any]:
    """Runs single build attempt with CREATE_NO_WINDOW."""
    if build_tool == "maven":
        cmd = ["mvn.cmd" if os.name == "nt" else "mvn", "clean", "package", "-B", "-DskipTests=false"]
    elif build_tool == "gradle":
        gradlew = os.path.join(project_dir, "gradlew.bat" if os.name == "nt" else "./gradlew")
        cmd = [gradlew if os.path.exists(gradlew) else "gradle", "build", "--no-daemon"]
    elif build_tool == "python":
        cmd = ["python", "-m", "unittest", "discover"]
    else:
        return {"code": 1, "output": f"Unknown build system in {project_dir}"}

    try:
        proc = subprocess.run(
            cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=NO_WINDOW
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return {
            "code": proc.returncode,
            "output": combined,
            "cmd": " ".join(cmd),
        }
    except Exception as e:
        return {"code": -1, "output": f"Execution error: {e}"}


def attempt_heal(project_dir: str, errors: List[Dict[str, Any]], brain=None) -> bool:
    """Uses Jarvis brain or regex fixer to repair offending code."""
    if not errors or not brain:
        return False

    healed_any = False
    import security

    for err in errors[:3]:  # heal up to 3 errors per cycle
        file_path = err["file"]
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_dir, file_path)

        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue

        err_line = err["line"]
        start = max(0, err_line - 15)
        end = min(len(lines), err_line + 15)
        snippet = "".join(f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start))

        # Ask brain for direct fix
        prompt = (
            f"You are repairing a compilation error in Java/Spigot project: {os.path.basename(file_path)}.\n"
            f"Error at line {err_line}: {err['message']}\n"
            f"Surrounding code snippet:\n```java\n{snippet}\n```\n"
            f"Respond ONLY with the complete corrected file content for {os.path.basename(file_path)}."
            f" Do not add explanations or conversational filler. Keep all other methods intact."
        )

        try:
            fixed_code = brain.ask(prompt, unattended=True)
            # Strip markdown block quotes if present
            if "```" in fixed_code:
                match = re.search(r"```(?:java)?\s*\n([\s\S]*?)```", fixed_code)
                if match:
                    fixed_code = match.group(1)

            if len(fixed_code.strip()) > 50:
                security.create_snapshot(file_path, description=f"Before auto-heal line {err_line}")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code.strip() + "\n")
                healed_any = True
                print(f"[DevLoop] Healed {os.path.basename(file_path)} at line {err_line}", flush=True)
        except Exception as heal_err:
            print(f"[DevLoop] Heal attempt failed on {file_path}: {heal_err}", flush=True)

    return healed_any


def build_and_heal(project_dir: str, max_retries: int = 3, brain=None) -> Dict[str, Any]:
    """Autonomous compile, test, and self-healing loop."""
    project_dir = os.path.abspath(project_dir)
    build_tool = detect_build_system(project_dir)

    if build_tool == "unknown":
        return {
            "success": False,
            "error": f"No recognized build file (pom.xml, build.gradle) found in {project_dir}",
            "project_dir": project_dir,
        }

    history = []
    for iteration in range(1, max_retries + 1):
        t0 = time.time()
        res = execute_build(project_dir, build_tool)
        duration = round(time.time() - t0, 1)

        if res["code"] == 0:
            artifact = find_artifact(project_dir, build_tool)
            return {
                "success": True,
                "healed": iteration > 1,
                "iterations": iteration,
                "duration": duration,
                "build_tool": build_tool,
                "artifact": artifact,
                "project_dir": project_dir,
                "history": history,
            }

        # Build failed: extract errors
        errors = parse_java_errors(res["output"])
        history.append({
            "iteration": iteration,
            "errors": errors[:5],
            "sample_output": res["output"][-1200:],
        })

        if iteration < max_retries and brain:
            healed = attempt_heal(project_dir, errors, brain=brain)
            if not healed:
                break
        else:
            break

    return {
        "success": False,
        "iterations": len(history),
        "build_tool": build_tool,
        "project_dir": project_dir,
        "errors": history[-1]["errors"] if history else [],
        "last_log": history[-1]["sample_output"] if history else "",
    }


def analyze_terminal_error(command: str, exit_code: int, output: str, cwd: str = "", brain=None) -> str:
    """Provides a fast, high-accuracy 1-line fix for terminal errors."""
    output = output or ""
    out_lower = output.lower()

    if "is not recognized as the name of a cmdlet" in out_lower or "command not found" in out_lower:
        cmd_name = command.split()[0] if command else "command"
        if cmd_name in ("mvn", "maven"):
            return "Install Maven or add Apache Maven bin to system PATH."
        if cmd_name in ("gradle", "./gradlew"):
            return "Use './gradlew' wrapper or install Gradle."
        return f"'{cmd_name}' not on PATH. Verify installation and environment variables."

    if "fatal: not a git repository" in out_lower:
        return "Run 'git init' to initialize a repository in this folder."

    m_pip = re.search(r"no module named ['\"]?([a-zA-Z0-9_\-]+)['\"]?", output, re.I)
    if m_pip:
        return f"Run 'pip install {m_pip.group(1)}' to install missing dependency."

    if "release version" in out_lower and "not supported" in out_lower:
        return "Target Java bytecode is higher than compiler. Set target in pom.xml to JDK 21 or 25."

    if "address already in use" in out_lower or "port already in use" in out_lower:
        m_port = re.search(r":(\d+)", output)
        port_num = m_port.group(1) if m_port else "port"
        return f"Port {port_num} occupied. Kill process with 'Stop-Process -Id (Get-NetTCPConnection -LocalPort {port_num}).OwningProcess -Force'."

    if "access is denied" in out_lower or "permission denied" in out_lower:
        return "Permission denied. Run terminal / PowerShell as Administrator."

    if brain and output:
        try:
            prompt = (
                f"A developer ran: `{command}` and got exit code {exit_code}.\n"
                f"Output snippet:\n{output[-600:]}\n\n"
                f"Give ONLY a single actionable sentence or command to fix this. Zero filler."
            )
            fix = brain.ask(prompt, unattended=True)
            return fix.strip()[:100]
        except Exception:
            pass

    return f"Command exited with code {exit_code}. Check compiler or execution logs."


def scaffold_spigot_template(target_dir: str, plugin_name: str = "JarvisScoutPlugin") -> str:
    """Scaffolds a clean, production-grade Paper 1.21+ plugin maven project."""
    os.makedirs(target_dir, exist_ok=True)
    java_dir = os.path.join(target_dir, "src", "main", "java", "com", "jarvis", plugin_name.lower())
    res_dir = os.path.join(target_dir, "src", "main", "resources")
    os.makedirs(java_dir, exist_ok=True)
    os.makedirs(res_dir, exist_ok=True)

    pom_xml = f"""<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.jarvis</groupId>
    <artifactId>{plugin_name.lower()}</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>21</maven.compiler.source>
        <maven.compiler.target>21</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <repositories>
        <repository>
            <id>papermc</id>
            <url>https://repo.papermc.io/repository/maven-public/</url>
        </repository>
    </repositories>

    <dependencies>
        <dependency>
            <groupId>io.papermc.paper</groupId>
            <artifactId>paper-api</artifactId>
            <version>1.21.4-R0.1-SNAPSHOT</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
</project>
"""
    plugin_yml = f"""name: {plugin_name}
version: '1.0.0'
main: com.jarvis.{plugin_name.lower()}.Main
api-version: '1.21'
author: Qssaf
description: Autonomous Spigot/Paper Plugin managed by Jarvis
"""
    main_java = f"""package com.jarvis.{plugin_name.lower()};

import org.bukkit.plugin.java.JavaPlugin;

public class Main extends JavaPlugin {{
    @Override
    public void onEnable() {{
        getLogger().info("{plugin_name} initialized and enabled by Jarvis!");
    }}

    @Override
    public void onDisable() {{
        getLogger().info("{plugin_name} disabled cleanly.");
    }}
}}
"""
    gdd_md = f"""# Game Design & Technical Specification: {plugin_name}

## 1. Executive Summary
Autonomous Spigot/Paper 1.21+ plugin architecture scaffolded for high-performance server gameplay.

## 2. Core Mechanics
- Real-time event handling via Paper-API.
- Low-latency packet interception & tick optimizations.
- Persistent state management via SQLite / YamlConfiguration.

## 3. Build & Test Cycle
- Compile: `mvn clean package`
- Auto-Deploy: Jarvis `test_spigot_plugin(action='deploy')`
- Hot-Reload: `reload confirm` / PlugManX
"""

    with open(os.path.join(target_dir, "pom.xml"), "w", encoding="utf-8") as f:
        f.write(pom_xml)
    with open(os.path.join(res_dir, "plugin.yml"), "w", encoding="utf-8") as f:
        f.write(plugin_yml)
    with open(os.path.join(java_dir, "Main.java"), "w", encoding="utf-8") as f:
        f.write(main_java)
    with open(os.path.join(target_dir, "GDD.md"), "w", encoding="utf-8") as f:
        f.write(gdd_md)

    return target_dir
