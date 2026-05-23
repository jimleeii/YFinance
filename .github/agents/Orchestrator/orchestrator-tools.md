# Orchestrator Tool Reference

This file contains the complete list of tools available to the Orchestrator agent. It is separated from the main `orchestrator.agent.md` to reduce token usage and improve readability.

## Tool Categories

### Agent Management
| Tool | Purpose |
|------|---------|
| `agent/runSubagent` | Dispatch tasks to Software Architect, Senior Developer, or Code Reviewer subagents |

### VSCode Workspace & Environment
| Tool | Purpose |
|------|---------|
| `vscode/getProjectSetupInfo` | Retrieve current project configuration and setup details |
| `vscode/installExtension` | Install VSCode extensions |
| `vscode/memory` | Access and manipulate agent memory storage |
| `vscode/newWorkspace` | Create a new workspace |
| `vscode/resolveMemoryFileUri` | Resolve URI for memory-backed files |
| `vscode/runCommand` | Execute VSCode commands |
| `vscode/vscodeAPI` | Access VSCode extension API |
| `vscode/extensions` | List and manage installed extensions |
| `vscode/askQuestions` | Prompt user for input within VSCode |

### Terminal Execution
| Tool | Purpose |
|------|---------|
| `execute/runNotebookCell` | Execute a Jupyter notebook cell |
| `execute/getTerminalOutput` | Retrieve output from terminal sessions |
| `execute/killTerminal` | Terminate a running terminal session |
| `execute/sendToTerminal` | Send commands to a terminal |
| `execute/createAndRunTask` | Create and execute a background task |
| `execute/runInTerminal` | Run a command in a terminal |
| `execute/runTests` | Execute test suites |
| `execute/testFailure` | Investigate test failures |

### File & Workspace Reading
| Tool | Purpose |
|------|---------|
| `read/getNotebookSummary` | Get summary of Jupyter notebook contents |
| `read/problems` | Read diagnostics/problems from the workspace |
| `read/readFile` | Read file contents |
| `read/viewImage` | View and analyze images |
| `read/terminalSelection` | Read selected terminal content |
| `read/terminalLastCommand` | Retrieve the last terminal command and its output |

### File Editing
| Tool | Purpose |
|------|---------|
| `edit/createDirectory` | Create new directories |
| `edit/createFile` | Create new files |
| `edit/createJupyterNotebook` | Create new Jupyter notebooks |
| `edit/editFiles` | Modify existing files |
| `edit/editNotebook` | Modify Jupyter notebooks |
| `edit/rename` | Rename files or directories |

### Search Operations
| Tool | Purpose |
|------|---------|
| `search/changes` | Search for recent changes in the workspace |
| `search/codebase` | Semantic search across codebase |
| `search/fileSearch` | Search for files by name/pattern |
| `search/listDirectory` | List directory contents |
| `search/textSearch` | Search for text patterns in files |
| `search/usages` | Find usages of symbols |

### Web & External Resources
| Tool | Purpose |
|------|---------|
| `web/fetch` | Fetch web page content |
| `web/githubRepo` | Interact with GitHub repositories |

### Browser Automation (Playwright)
| Tool | Purpose |
|------|---------|
| `browser/openBrowserPage` | Open a new browser page |
| `browser/readPage` | Read current page content |
| `browser/screenshotPage` | Capture page screenshot |
| `browser/navigatePage` | Navigate to a URL |
| `browser/clickElement` | Click on page elements |
| `browser/dragElement` | Drag and drop elements |
| `browser/hoverElement` | Hover over elements |
| `browser/typeInPage` | Type text into page |
| `browser/runPlaywrightCode` | Execute custom Playwright code |
| `browser/handleDialog` | Handle browser dialogs (alert/confirm/prompt) |

### Python Environment (ms-python.python extension)
| Tool | Purpose |
|------|---------|
| `ms-python.python/getPythonEnvironmentInfo` | Get Python environment details |
| `ms-python.python/getPythonExecutableCommand` | Get Python executable path |
| `ms-python.python/installPythonPackage` | Install Python packages |
| `ms-python.python/configurePythonEnvironment` | Configure Python environment settings |

### Task Management
| Tool | Purpose |
|------|---------|
| `todo` | Manage task lists and track progress |

## Usage Notes

- All tools require appropriate permissions and context within the active workspace
- Browser automation tools require Playwright to be installed
- Python tools require the ms-python.python extension to be installed and activated
- File operations respect workspace boundaries - you cannot access files outside the current workspace

## See Also

- `skills/model-policy/SKILL.md` - For model selection when using subagent dispatch
- `skills/quality-policy/SKILL.md` - For quality standards when generating or modifying files