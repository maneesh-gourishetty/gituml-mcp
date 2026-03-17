# GitUML — Java / Spring Boot UML Generator + MCP Server

> Generate UML class diagrams, sequence diagrams, flowcharts, and component diagrams from **any Java or Spring Boot repository** — via CLI or directly inside Claude Desktop as an MCP server.

---

## Features

- **5 MCP tools** exposed to Claude Desktop: `analyze_repo`, `generate_class_diagram`, `generate_sequence_diagram`, `generate_flowchart`, `generate_component_diagram`
- Works with **GitHub/GitLab URLs** (shallow clone) or **local paths**
- Detects project type: `pure_java`, `spring_boot`, `spring_mvc`
- Detects build system: `maven`, `gradle`, `none`
- Annotation-aware **Spring layer detection** (Controller → Service → Repository → Model → Config → Messaging)
- Output in **Mermaid**, **PlantUML**, or **both**
- Test directories excluded by default

---

## Project Structure

```
gituml/
├── server.py              ← MCP server (FastMCP, STDIO transport)
├── main.py                ← CLI entry point (argparse)
├── test_server.py         ← Quick smoke-test for server tools
├── requirements.txt
├── claude_desktop_config.json
├── core/
│   ├── models.py          ← Data models: ClassMeta, MethodMeta, RepoMetadata, …
│   └── java_parser.py     ← javalang-based Java AST parser
└── diagrams/
    ├── class_diagram.py
    ├── sequence_diagram.py
    ├── flowchart.py
    └── component_diagram.py
```

---

## Requirements

- Python **3.10+**
- Git installed and available on `PATH` (needed for cloning remote repos)

```bash
pip install -r requirements.txt
```

`requirements.txt` installs:

| Package | Purpose |
|---------|---------|
| `javalang` | Java AST parsing |
| `gitpython` | Shallow-clone remote repositories |
| `mcp[cli]` | FastMCP server / STDIO transport |

---

## Usage — CLI

```bash
# From a GitHub URL
python main.py --repo https://github.com/spring-projects/spring-petclinic

# From a local path
python main.py --repo /path/to/my-spring-app

# With sequence diagram entry point
python main.py --repo /path/to/my-app \
               --entry-class UserController \
               --entry-method createUser

# With method-level flowchart
python main.py --repo /path/to/my-app \
               --flow-class OrderService \
               --flow-method processOrder

# Custom output directory, Mermaid only
python main.py --repo /path/to/my-app --output-dir ./diagrams --format mermaid

# Include test directories
python main.py --repo /path/to/my-app --include-tests

# Limit class diagram to 30 classes
python main.py --repo /path/to/my-app --max-classes 30
```

### CLI Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--repo` | `-r` | *(required)* | GitHub URL or local path |
| `--output-dir` | `-o` | `./output` | Directory for output `.md` files |
| `--entry-class` | `-ec` | `None` | Class for sequence diagram entry point |
| `--entry-method` | `-em` | `None` | Method to trace in sequence diagram |
| `--flow-class` | `-fc` | `None` | Class for method-level flowchart |
| `--flow-method` | `-fm` | `None` | Method for method-level flowchart |
| `--format` | | `both` | `mermaid` \| `plantuml` \| `both` |
| `--max-classes` | | `60` | Max classes in class diagram |
| `--include-tests` | | `False` | Include test source directories |

### Output Files

All written to `./output/` by default:

```
output/
├── class_diagram.md
├── component_diagram.md
├── sequence_diagram.md
└── flowchart.md
```

Preview `.md` files in VS Code with the **Markdown Preview Enhanced** extension (`Ctrl+Shift+V` / `Cmd+Shift+V`).

---

## Usage — MCP Server (Claude Desktop)

### Step 1 — Install Claude Desktop

Download from [https://claude.ai/download](https://claude.ai/download)

### Step 2 — Locate the config file

| OS | Path |
|----|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Step 3 — Register GitUML

Open the config file and add the `gituml` entry:

**Windows**
```json
{
  "mcpServers": {
    "gituml": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\projects\\gituml\\server.py"]
    }
  }
}
```

**macOS / Linux**
```json
{
  "mcpServers": {
    "gituml": {
      "command": "python3",
      "args": ["/home/yourname/projects/gituml/server.py"]
    }
  }
}
```

> **Windows note:** Use double backslashes `\\` in paths inside JSON.

### Step 4 — Restart Claude Desktop

After saving the config, fully quit and relaunch Claude Desktop.

Look for the **tools (hammer) icon** in the chat input bar — click it to confirm these tools are loaded:

- `analyze_repo`
- `generate_class_diagram`
- `generate_sequence_diagram`
- `generate_flowchart`
- `generate_component_diagram`
- `generate_all`

### Step 5 — Talk to Claude

```
Analyse this repo: https://github.com/spring-projects/spring-petclinic

Generate a class diagram for C:/projects/my-spring-app

Show me the sequence diagram for UserController.createUser

Generate a flowchart for the processOrder method in OrderService

Show the component architecture of https://github.com/myorg/myrepo

Generate all diagrams for https://github.com/user/repo and save to ./output
```

---

## MCP Tools Reference

### `analyze_repo`

Returns a structured summary of the repository — no diagrams generated.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | `str` | ✅ | GitHub URL or local path |

**Returns:** Project type, build system, package list, layer breakdown, dependency graph.

---

### `generate_class_diagram`

Generates a UML class diagram showing classes, fields, methods, inheritance, and Spring layers.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | `str` | *(required)* | GitHub URL or local path |
| `output_dir` | `str` | `""` | Write to file if provided, else return as string |
| `format` | `str` | `"both"` | `mermaid` \| `plantuml` \| `both` |
| `package_filter` | `str` | `None` | Filter to classes in this package prefix |
| `max_classes` | `int` | `60` | Max classes to include |

---

### `generate_sequence_diagram`

Traces the call chain from an entry point across Spring layers.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | `str` | *(required)* | GitHub URL or local path |
| `output_dir` | `str` | `""` | Write to file if provided |
| `format` | `str` | `"both"` | Output format |
| `entry_class` | `str` | `None` | Starting class (e.g. `UserController`) |
| `entry_method` | `str` | `None` | Starting method (e.g. `createUser`) |

---

### `generate_flowchart`

Generates a control-flow diagram for a specific method, or a high-level architecture flowchart.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | `str` | *(required)* | GitHub URL or local path |
| `output_dir` | `str` | `""` | Write to file if provided |
| `format` | `str` | `"both"` | Output format |
| `target_class` | `str` | `None` | Class containing the target method |
| `target_method` | `str` | `None` | Method to flowchart |

---

### `generate_component_diagram`

High-level architecture view — components grouped by Spring layer or package.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | `str` | *(required)* | GitHub URL or local path |
| `output_dir` | `str` | `""` | Write to file if provided |
| `format` | `str` | `"both"` | Output format |

---

### `generate_all`

Generates all 4 diagrams and writes them to disk — equivalent to running `main.py` from the CLI.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | `str` | *(required)* | GitHub URL or local path |
| `output_dir` | `str` | `"output"` | Directory to write all 4 `.md` files |
| `format` | `str` | `"both"` | Output format |
| `entry_class` | `str` | `""` | Sequence diagram entry class |
| `entry_method` | `str` | `""` | Sequence diagram entry method |
| `flow_class` | `str` | `""` | Flowchart target class |
| `flow_method` | `str` | `""` | Flowchart target method |
| `include_tests` | `bool` | `False` | Include test source directories |
| `max_classes` | `int` | `60` | Max classes in class diagram |

---

## Supported

| Category | Detail |
|----------|--------|
| Languages | Java (via `javalang` AST parser) |
| Frameworks | Plain Java, Spring Boot, Spring MVC |
| Build tools | Maven (`pom.xml`), Gradle (`build.gradle`) |
| Sources | GitHub URLs, GitLab URLs, local paths |
| Output | Mermaid, PlantUML, or both |
| Spring layers | controller, service, repository, model, config, messaging, scheduler |

---

## Troubleshooting

**`No Java classes found`** — Confirm the path points to a Java project root. Check that `.java` files exist under `src/`.

**`Failed to clone repo`** — Verify `git` is on your `PATH` and the URL is accessible. Private repos require SSH key or credential setup.

**`gitpython not installed`** — Run `pip install gitpython`.

**Claude Desktop tools not appearing** — Check the JSON config for syntax errors (trailing commas, wrong path separators on Windows). Fully quit and relaunch Claude Desktop.

**MCP server not starting** — Test the server directly: `python server.py` — it should block silently (waiting on STDIO). Any Python import errors will surface here.

---
