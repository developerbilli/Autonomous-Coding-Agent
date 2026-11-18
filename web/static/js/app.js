/**
 * Autonomous AI Multi-Agent Coding System — Frontend Controller
 * Connects to FastAPI backend and streams execution via Server-Sent Events (SSE).
 * Features 5 distinct specialized agents and LangSmith-style Node Inspector.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const btnLaunch = document.getElementById("btn-launch");
    const btnBrowseFolder = document.getElementById("btn-browse-folder");
    const btnBrowseInline = document.getElementById("btn-browse-inline");
    const localDirFilePicker = document.getElementById("local-dir-file-picker");
    const btnClearLogs = document.getElementById("btn-clear-logs");
    const btnRefreshSymbols = document.getElementById("btn-refresh-symbols");

    const archModeSelect = document.getElementById("arch-mode");
    const repoPathInput = document.getElementById("repo-path");
    const taskPromptInput = document.getElementById("task-prompt");
    const taskTypeSelect = document.getElementById("task-type");
    const maxIterInput = document.getElementById("max-iter");
    const iterValDisplay = document.getElementById("iter-val");
    const demoModeCheck = document.getElementById("demo-mode-check");

    const langsmithBadge = document.getElementById("langsmith-badge");
    const langsmithLink = document.getElementById("langsmith-link");
    const agentStatePill = document.getElementById("agent-state-pill");
    const agentStateText = document.getElementById("agent-state-text");
    const pipelineStatus = document.getElementById("pipeline-status");

    const terminalFeed = document.getElementById("terminal-feed");
    const symbolsContainer = document.getElementById("symbols-container");
    const symbolCountPill = document.getElementById("symbol-count-pill");
    const symbolFilterInput = document.getElementById("symbol-filter");
    const pytestOutput = document.getElementById("pytest-output");
    const testStatusBanner = document.getElementById("test-status-banner");
    const reportContainer = document.getElementById("report-container");

    // Drawer Elements
    const nodeDrawer = document.getElementById("node-inspector-drawer");
    const drawerBackdrop = document.getElementById("drawer-backdrop");
    const btnCloseDrawer = document.getElementById("btn-close-drawer");
    const drawerNodeName = document.getElementById("drawer-node-name");
    const drawerNodeType = document.getElementById("drawer-node-type");
    const drawerNodeIcon = document.getElementById("drawer-node-icon");
    const drawerNodeLatency = document.getElementById("drawer-node-latency");
    const drawerNodeStatus = document.getElementById("drawer-node-status");
    const drawerJsonInputs = document.getElementById("drawer-json-inputs");
    const drawerJsonOutputs = document.getElementById("drawer-json-outputs");
    const drawerMetaContent = document.getElementById("drawer-meta-content");

    // Ingestion Source Tabs
    const sourceTabs = document.querySelectorAll(".source-tab");
    const sourcePanes = {
        local: document.getElementById("source-pane-local"),
        github: document.getElementById("source-pane-github"),
        zip: document.getElementById("source-pane-zip"),
        greenfield: document.getElementById("source-pane-greenfield"),
    };
    let activeSourceType = "local";

    function setSourceTab(type) {
        if (!sourcePanes[type]) return;
        activeSourceType = type;
        sourceTabs.forEach(t => {
            if (t.getAttribute("data-source") === type) {
                t.classList.add("active");
            } else {
                t.classList.remove("active");
            }
        });
        Object.entries(sourcePanes).forEach(([key, pane]) => {
            if (pane) pane.style.display = (key === activeSourceType) ? "flex" : "none";
        });
    }

    sourceTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            setSourceTab(tab.getAttribute("data-source"));
        });
    });

    const githubUrlInput = document.getElementById("github-url");
    const githubBranchInput = document.getElementById("github-branch");
    const githubTokenInput = document.getElementById("github-token");
    const isolateLocalCheck = document.getElementById("isolate-local-check");
    const operatorAttestationCheck = document.getElementById("operator-attestation-check");
    const zipFileInput = document.getElementById("zip-file");
    const zipProjectNameInput = document.getElementById("zip-project-name");
    const greenfieldNameInput = document.getElementById("greenfield-name");

    // Auto-normalize GitHub URLs when pasted
    if (githubUrlInput) {
        githubUrlInput.addEventListener("input", () => {
            const val = githubUrlInput.value.trim();
            const ghMatch = val.match(/^https?:\/\/github\.com\/([^\/]+)\/([^\/]+)(?:\/(?:blob|tree)\/([^\/]+)(?:\/(.*))?)?/);
            if (ghMatch) {
                const owner = ghMatch[1];
                const repo = ghMatch[2].replace(/\.git$/i, "");
                const urlBranch = ghMatch[3];
                const filePath = ghMatch[4];
                githubUrlInput.value = `https://github.com/${owner}/${repo}`;
                if (urlBranch && githubBranchInput) {
                    githubBranchInput.value = urlBranch;
                }
                if (filePath && taskPromptInput && (!taskPromptInput.value.trim() || taskPromptInput.value.includes("Calculator"))) {
                    taskPromptInput.value = `Refactor ${filePath} into a reusable, modular function with input validation, error handling, and pytest unit tests.`;
                }
            }
        });
    }

    // Support deep-linking via query parameters (e.g. ?source=github&url=...&task=...)
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const paramSource = urlParams.get("source");
        const paramUrl = urlParams.get("url") || urlParams.get("github_url");
        const paramBranch = urlParams.get("branch");
        const paramTask = urlParams.get("task");
        const paramAutorun = urlParams.get("autorun") === "true";

        if (paramSource && sourcePanes[paramSource]) {
            setSourceTab(paramSource);
        }
        if (paramUrl) {
            setSourceTab("github");
            const ghMatch = paramUrl.match(/^https?:\/\/github\.com\/([^\/]+)\/([^\/]+)(?:\/(?:blob|tree)\/([^\/]+)(?:\/(.*))?)?/);
            if (ghMatch) {
                const owner = ghMatch[1];
                const repo = ghMatch[2].replace(/\.git$/i, "");
                const urlBranch = ghMatch[3] || paramBranch || "main";
                const filePath = ghMatch[4];
                githubUrlInput.value = `https://github.com/${owner}/${repo}`;
                if (githubBranchInput) githubBranchInput.value = urlBranch;
                if (filePath && taskPromptInput && (!taskPromptInput.value.trim() || taskPromptInput.value.includes("Calculator"))) {
                    taskPromptInput.value = `Refactor ${filePath} into a reusable, modular function with input validation, error handling, and pytest unit tests.`;
                }
            } else {
                githubUrlInput.value = paramUrl;
            }
        }
        if (paramBranch && githubBranchInput) {
            githubBranchInput.value = paramBranch;
        }
        if (paramTask && taskPromptInput) {
            taskPromptInput.value = paramTask;
        }
        if (paramAutorun) {
            setTimeout(() => {
                if (btnLaunch && !isRunning) {
                    btnLaunch.click();
                }
            }, 900);
        }
    } catch (e) {
        console.warn("Could not parse query parameters:", e);
    }

    let isRunning = false;
    let allSymbols = [];

    // 5-Agent Multi-Agent Tracing Store
    const nodeTraces = {
        explore_repo: {
            name: "explore_repo",
            icon: "🔍",
            type: "AST Static Indexer",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        manager_planner: {
            name: "manager_planner",
            icon: "👑",
            type: "ManagerPlannerAgent",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        coder: {
            name: "coder",
            icon: "💻",
            type: "CoderAgent",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        test_generator: {
            name: "test_generator",
            icon: "🧪",
            type: "TestGeneratorAgent",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        sandbox_runner: {
            name: "sandbox_runner",
            icon: "🛡️",
            type: "Execution Sandbox Subprocess",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        debugger: {
            name: "debugger",
            icon: "🔄",
            type: "DebuggerAgent",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        reviewer: {
            name: "reviewer",
            icon: "🛡️",
            type: "ReviewerAgent",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
        manager_finalize: {
            name: "manager_finalize",
            icon: "✅",
            type: "Manager Verification Finalizer",
            status: "PENDING",
            latency_ms: 0,
            inputs: {},
            outputs: {},
        },
    };

    // ==========================================
    // 1. Initial Status Check
    // ==========================================
    async function checkStatus() {
        try {
            const res = await fetch("/api/status");
            if (!res.ok) return;
            const data = await res.json();

            // LangSmith Status
            if (data.langsmith && data.langsmith.enabled) {
                langsmithBadge.className = "status-pill online";
                langsmithBadge.querySelector(".status-text").textContent = `LangSmith: Active (${data.langsmith.project})`;
                langsmithLink.style.display = "inline";
            } else {
                langsmithBadge.className = "status-pill offline";
                langsmithBadge.querySelector(".status-text").textContent = "LangSmith: Offline (Local)";
            }
        } catch (err) {
            console.warn("Status check failed:", err);
        }
    }

    checkStatus();

    // Max Iterations Slider
    maxIterInput.addEventListener("input", (e) => {
        iterValDisplay.textContent = e.target.value;
    });

    // Preset Chips
    document.querySelectorAll(".preset-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            taskPromptInput.value = chip.getAttribute("data-task");
            const type = chip.getAttribute("data-type");
            if (type) taskTypeSelect.value = type;
            if (chip.getAttribute("data-demo") === "true") {
                demoModeCheck.checked = true;
            }
        });
    });

    // =========================================================================
    // Folder Chooser Modal Logic (In-Browser Directory Explorer)
    // =========================================================================
    const folderModal = document.getElementById("folder-modal");
    const folderModalBackdrop = document.getElementById("folder-modal-backdrop");
    const btnCloseFolderModal = document.getElementById("btn-close-folder-modal");
    const btnCancelFolderModal = document.getElementById("btn-cancel-folder-modal");
    const btnConfirmFolderModal = document.getElementById("btn-confirm-folder-modal");
    const folderBookmarksContainer = document.getElementById("folder-modal-bookmarks");
    const folderBreadcrumbsContainer = document.getElementById("folder-breadcrumbs");
    const folderListContainer = document.getElementById("folder-list");
    const folderListLoading = document.getElementById("folder-list-loading");
    const folderSearchInput = document.getElementById("folder-search-input");
    const folderSelectedPathInput = document.getElementById("folder-selected-path");
    const btnFolderUp = document.getElementById("btn-folder-up");
    const btnFolderRefresh = document.getElementById("btn-folder-refresh");

    let currentBrowsePath = "";
    let parentBrowsePath = null;
    let selectedDirectoryPath = "";
    let loadedFolders = [];

    function openFolderModal(initialPath) {
        if (!folderModal || !folderModalBackdrop) return;
        folderModal.classList.add("open");
        folderModalBackdrop.classList.add("open");
        const startPath = (initialPath && initialPath.trim()) ? initialPath.trim() : (repoPathInput ? repoPathInput.value.trim() : "");
        loadDirectory(startPath);
        if (folderSearchInput) {
            folderSearchInput.value = "";
            folderSearchInput.focus();
        }
    }

    function closeFolderModal() {
        if (!folderModal || !folderModalBackdrop) return;
        folderModal.classList.remove("open");
        folderModalBackdrop.classList.remove("open");
    }

    async function loadDirectory(path) {
        if (!folderListContainer) return;
        if (folderListLoading) folderListLoading.style.display = "flex";
        folderListContainer.innerHTML = "";

        try {
            const url = path ? `/api/fs/browse?path=${encodeURIComponent(path)}` : "/api/fs/browse";
            const res = await fetch(url);
            const data = await res.json();

            if (!data.success) {
                folderListContainer.innerHTML = `<div class="folder-empty">⚠️ ${data.error || "Could not read directory."}</div>`;
                return;
            }

            currentBrowsePath = data.current_path;
            parentBrowsePath = data.parent_path;
            selectedDirectoryPath = data.current_path;
            if (folderSelectedPathInput) folderSelectedPathInput.value = data.current_path;

            if (btnFolderUp) {
                btnFolderUp.disabled = !parentBrowsePath;
            }

            // Render Bookmarks
            if (folderBookmarksContainer && data.bookmarks) {
                folderBookmarksContainer.innerHTML = "";
                data.bookmarks.forEach(bm => {
                    const chip = document.createElement("button");
                    chip.type = "button";
                    chip.className = "folder-bookmark-chip";
                    chip.innerHTML = `<span>${bm.icon || "📁"}</span><span>${bm.name}</span>`;
                    chip.title = bm.path;
                    chip.addEventListener("click", () => loadDirectory(bm.path));
                    folderBookmarksContainer.appendChild(chip);
                });
            }

            // Render Breadcrumbs
            if (folderBreadcrumbsContainer && data.breadcrumbs) {
                folderBreadcrumbsContainer.innerHTML = "";
                data.breadcrumbs.forEach((crumb, idx) => {
                    if (idx > 0) {
                        const sep = document.createElement("span");
                        sep.className = "folder-breadcrumb-sep";
                        sep.textContent = "/";
                        folderBreadcrumbsContainer.appendChild(sep);
                    }
                    const pill = document.createElement("span");
                    pill.className = "folder-breadcrumb-pill";
                    pill.textContent = crumb.name;
                    pill.title = crumb.path;
                    pill.addEventListener("click", () => loadDirectory(crumb.path));
                    folderBreadcrumbsContainer.appendChild(pill);
                });
                folderBreadcrumbsContainer.scrollLeft = folderBreadcrumbsContainer.scrollWidth;
            }

            loadedFolders = data.folders || [];
            renderFolderList(folderSearchInput ? folderSearchInput.value : "");

        } catch (err) {
            folderListContainer.innerHTML = `<div class="folder-empty">⚠️ Error loading directory: ${err.message}</div>`;
        } finally {
            if (folderListLoading) folderListLoading.style.display = "none";
        }
    }

    function renderFolderList(filterText = "") {
        if (!folderListContainer) return;
        folderListContainer.innerHTML = "";

        const query = (filterText || "").trim().toLowerCase();
        const filtered = loadedFolders.filter(f => !query || f.name.toLowerCase().includes(query));

        if (filtered.length === 0) {
            folderListContainer.innerHTML = `<div class="folder-empty">No subdirectories found in this folder.</div>`;
            return;
        }

        filtered.forEach(item => {
            const el = document.createElement("div");
            el.className = "folder-item";
            if (item.path === selectedDirectoryPath) {
                el.classList.add("selected");
            }

            const gitBadge = item.is_git ? `<span class="folder-badge-git">GIT</span>` : "";
            const codeIcon = item.has_code ? "📦" : "📁";

            el.innerHTML = `
                <div class="folder-item-left">
                    <span class="folder-item-icon">${codeIcon}</span>
                    <span class="folder-item-name" title="${item.path}">${item.name}</span>
                </div>
                <div class="folder-item-meta">
                    ${gitBadge}
                    <span class="folder-item-arrow">➜</span>
                </div>
            `;

            // Single click selects
            el.addEventListener("click", () => {
                document.querySelectorAll(".folder-item").forEach(node => node.classList.remove("selected"));
                el.classList.add("selected");
                selectedDirectoryPath = item.path;
                if (folderSelectedPathInput) folderSelectedPathInput.value = item.path;
            });

            // Double click opens directory
            el.addEventListener("dblclick", () => {
                loadDirectory(item.path);
            });

            folderListContainer.appendChild(el);
        });
    }

    function cleanPath(val) {
        if (!val) return "";
        return val.replace(/^["']|["']$/g, "").replace(/^[\r\n]+|[\r\n]+$/g, "");
    }

    function confirmFolderSelection() {
        let path = folderSelectedPathInput ? cleanPath(folderSelectedPathInput.value) : selectedDirectoryPath;
        if (!path) {
            alert("Please choose a valid folder.");
            return;
        }
        if (repoPathInput) {
            repoPathInput.value = path;
        }
        closeFolderModal();
        fetchSymbols();
        addTerminalLog("system", `📂 Local repository selected: ${path}`);
    }

    if (btnBrowseFolder) btnBrowseFolder.addEventListener("click", () => openFolderModal(repoPathInput ? repoPathInput.value : ""));
    if (btnBrowseInline) btnBrowseInline.addEventListener("click", () => openFolderModal(repoPathInput ? repoPathInput.value : ""));
    if (btnCloseFolderModal) btnCloseFolderModal.addEventListener("click", closeFolderModal);
    if (btnCancelFolderModal) btnCancelFolderModal.addEventListener("click", closeFolderModal);
    if (folderModalBackdrop) folderModalBackdrop.addEventListener("click", closeFolderModal);
    if (btnConfirmFolderModal) btnConfirmFolderModal.addEventListener("click", confirmFolderSelection);

    if (btnFolderUp) {
        btnFolderUp.addEventListener("click", () => {
            if (parentBrowsePath) loadDirectory(parentBrowsePath);
        });
    }

    if (btnFolderRefresh) {
        btnFolderRefresh.addEventListener("click", () => {
            loadDirectory(currentBrowsePath);
        });
    }

    if (folderSearchInput) {
        folderSearchInput.addEventListener("input", (e) => {
            renderFolderList(e.target.value);
        });
        folderSearchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                const firstItem = folderListContainer ? folderListContainer.querySelector(".folder-item") : null;
                if (firstItem) {
                    firstItem.click();
                    confirmFolderSelection();
                }
            } else if (e.key === "Escape") {
                closeFolderModal();
            }
        });
    }

    if (folderSelectedPathInput) {
        folderSelectedPathInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                confirmFolderSelection();
            } else if (e.key === "Escape") {
                closeFolderModal();
            }
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && folderModal && folderModal.classList.contains("open")) {
            closeFolderModal();
        }
    });

    if (localDirFilePicker) {
        localDirFilePicker.addEventListener("change", (e) => {
            const files = e.target.files;
            if (files && files.length > 0) {
                const folderName = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : files[0].name;
                repoPathInput.value = folderName;
                fetchSymbols();
                addTerminalLog("info", `Selected folder: ${folderName}`);
            }
        });
    }

    // Clear Terminal Logs
    btnClearLogs.addEventListener("click", () => {
        terminalFeed.innerHTML = "";
        addTerminalLog("system", "Terminal logs cleared.");
    });

    // Tab Switching
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");

    tabBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            const tabId = btn.getAttribute("data-tab");
            switchTab(tabId);
        });
    });

    function switchTab(tabId) {
        tabBtns.forEach((b) => b.classList.remove("active"));
        tabPanes.forEach((p) => p.classList.remove("active"));

        const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
        const targetPane = document.getElementById(tabId);

        if (targetBtn && targetPane) {
            targetBtn.classList.add("active");
            targetPane.classList.add("active");
        }
    }

    // ==========================================
    // 2. Terminal Logger
    // ==========================================
    function addTerminalLog(level, message, timeStr = null) {
        const line = document.createElement("div");
        line.className = `terminal-line ${level}`;

        const timestamp = timeStr || new Date().toTimeString().split(" ")[0];
        line.innerHTML = `
            <span class="time">[${timestamp}]</span>
            <span class="msg">${escapeHtml(message)}</span>
        `;

        terminalFeed.appendChild(line);
        terminalFeed.scrollTop = terminalFeed.scrollHeight;
    }

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    // ==========================================
    // 3. AST Symbol Scanner & Filtering
    // ==========================================
    async function fetchSymbols() {
        const repo = cleanPath(repoPathInput ? repoPathInput.value : "");
        if (!repo) {
            renderSymbols([]);
            symbolCountPill.textContent = "0";
            return;
        }
        try {
            const res = await fetch(`/api/symbols?repo=${encodeURIComponent(repo)}`);
            const data = await res.json();
            if (data.symbols) {
                allSymbols = data.symbols;
                renderSymbols(allSymbols);
                symbolCountPill.textContent = allSymbols.length;
                addTerminalLog("info", `AST Scanner: Indexed ${allSymbols.length} symbols in ${repo}`);
            }
        } catch (err) {
            addTerminalLog("error", `Failed to load symbols: ${err.message}`);
        }
    }

    function renderSymbols(symbols) {
        if (!symbols || symbols.length === 0) {
            symbolsContainer.innerHTML = `<div class="empty-state">No matching symbols found.</div>`;
            return;
        }

        symbolsContainer.innerHTML = symbols
            .map(
                (sym) => `
            <div class="symbol-card">
                <div class="symbol-header">
                    <span class="symbol-name">${escapeHtml(sym.name)}</span>
                    <span class="symbol-kind">${sym.kind}</span>
                </div>
                <div class="symbol-file">${escapeHtml(sym.file)} (Lines ${sym.lines})</div>
                <div class="symbol-meta">
                    <span>Args: ${sym.arguments ? sym.arguments.join(", ") || "none" : "none"}</span>
                </div>
            </div>
        `
            )
            .join("");
    }

    symbolFilterInput.addEventListener("input", (e) => {
        const q = e.target.value.toLowerCase();
        const filtered = allSymbols.filter(
            (s) => s.name.toLowerCase().includes(q) || s.file.toLowerCase().includes(q)
        );
        renderSymbols(filtered);
    });

    btnRefreshSymbols.addEventListener("click", fetchSymbols);

    // ==========================================
    // 4. LangGraph Node Visualizer & Pipeline State
    // ==========================================
    const flowNodes = document.querySelectorAll(".flow-node");

    function resetPipeline() {
        flowNodes.forEach((node) => {
            const isLoop = node.classList.contains("loop-node");
            node.className = `flow-node clickable ${isLoop ? "loop-node" : ""}`;
            node.querySelector(".node-status").textContent = "Pending";
            const lat = node.querySelector(".node-latency");
            if (lat) lat.textContent = "-- ms";
        });
        pipelineStatus.textContent = "Workflow Running...";

        Object.keys(nodeTraces).forEach((k) => {
            nodeTraces[k].status = "PENDING";
            nodeTraces[k].latency_ms = 0;
            nodeTraces[k].inputs = {};
            nodeTraces[k].outputs = {};
        });
    }

    function setNodeState(nodeName, state, customStatus = null, latency = null) {
        const el = document.getElementById(`node-${nodeName}`);
        if (!el) return;

        el.classList.remove("active", "done", "failed", "skipped");
        if (state) el.classList.add(state);

        const statusEl = el.querySelector(".node-status");
        if (statusEl) {
            if (customStatus) {
                statusEl.textContent = customStatus;
            } else if (state === "active") {
                statusEl.textContent = "Running";
            } else if (state === "done") {
                statusEl.textContent = "Done";
            } else if (state === "failed") {
                statusEl.textContent = "Failed";
            } else if (state === "skipped") {
                statusEl.textContent = "Skipped";
            }
        }

        if (latency !== null) {
            const latEl = document.getElementById(`latency-${nodeName}`);
            if (latEl) latEl.textContent = `${latency} ms`;
            if (nodeTraces[nodeName]) nodeTraces[nodeName].latency_ms = latency;
        }

        if (nodeTraces[nodeName]) {
            nodeTraces[nodeName].status = customStatus || state.toUpperCase();
        }
    }

    // ==========================================
    // 5. LangSmith-Style Node Inspector Drawer
    // ==========================================
    flowNodes.forEach((nodeEl) => {
        nodeEl.addEventListener("click", () => {
            const nodeKey = nodeEl.getAttribute("data-node");
            openNodeInspector(nodeKey);
        });
    });

    function openNodeInspector(nodeKey) {
        const trace = nodeTraces[nodeKey];
        if (!trace) return;

        drawerNodeName.textContent = trace.name;
        drawerNodeType.textContent = trace.type;
        drawerNodeIcon.textContent = trace.icon;
        drawerNodeLatency.textContent = `⏱️ ${trace.latency_ms || 0} ms`;

        drawerNodeStatus.textContent = trace.status;
        drawerNodeStatus.className = "badge-status";
        if (trace.status === "DONE" || trace.status === "PASSED" || trace.status === "RESOLVED") {
            drawerNodeStatus.classList.add("success");
        } else if (trace.status === "FAILED") {
            drawerNodeStatus.classList.add("failed");
        } else if (trace.status === "SKIPPED") {
            drawerNodeStatus.classList.add("skipped");
        }

        drawerJsonInputs.textContent =
            Object.keys(trace.inputs).length > 0
                ? JSON.stringify(trace.inputs, null, 2)
                : "// No inputs recorded for this specialist yet.";

        drawerJsonOutputs.textContent =
            Object.keys(trace.outputs).length > 0
                ? JSON.stringify(trace.outputs, null, 2)
                : "// No structured outputs returned yet.";

        drawerMetaContent.innerHTML = `
            <div class="meta-item">
                <span class="meta-label">Specialist Role:</span>
                <span class="meta-val">${trace.name}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Agent Class:</span>
                <span class="meta-val">${trace.type}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Execution Latency:</span>
                <span class="meta-val">${trace.latency_ms} ms</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Gate Status:</span>
                <span class="meta-val">${trace.status}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">LangSmith Sync:</span>
                <span class="meta-val">Verified Streamed</span>
            </div>
        `;

        nodeDrawer.classList.add("open");
        drawerBackdrop.classList.add("open");
    }

    function closeNodeInspector() {
        nodeDrawer.classList.remove("open");
        drawerBackdrop.classList.remove("open");
    }

    btnCloseDrawer.addEventListener("click", closeNodeInspector);
    drawerBackdrop.addEventListener("click", closeNodeInspector);

    // Drawer Sub-tab Switching
    document.querySelectorAll(".drawer-tab").forEach((tabBtn) => {
        tabBtn.addEventListener("click", () => {
            document.querySelectorAll(".drawer-tab").forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".drawer-pane").forEach((p) => p.classList.remove("active"));

            tabBtn.classList.add("active");
            const paneId = tabBtn.getAttribute("data-drawer-tab");
            document.getElementById(paneId).classList.add("active");
        });
    });

    // ==========================================
    // 6. Streaming Agent Execution (SSE)
    // ==========================================
    btnLaunch.addEventListener("click", async () => {
        if (isRunning) return;

        const task = taskPromptInput.value.trim();
        const maxIter = parseInt(maxIterInput.value, 10);
        const taskType = taskTypeSelect.value;
        const demoMode = demoModeCheck.checked;
        const mode = archModeSelect.value;

        if (!task) {
            alert("Please enter a coding task requirement.");
            return;
        }

        // Resolve parameters based on active ingestion tab
        let githubUrl = null;
        let branch = "main";
        let authToken = null;
        let localPath = repoPathInput ? cleanPath(repoPathInput.value) : "";
        let zipBase64 = null;
        let projectName = null;
        let isolateLocal = isolateLocalCheck ? isolateLocalCheck.checked : false;
        let displayTarget = localPath;

        if (activeSourceType === "local") {
            if (!localPath) {
                alert("Please choose or enter a local repository directory.");
                return;
            }
            displayTarget = localPath;
        } else if (activeSourceType === "github") {
            githubUrl = githubUrlInput ? githubUrlInput.value.trim() : "";
            if (!githubUrl) {
                alert("Please enter a valid GitHub repository URL.");
                return;
            }
            branch = (githubBranchInput && githubBranchInput.value.trim()) || "main";
            authToken = (githubTokenInput && githubTokenInput.value.trim()) || null;
            localPath = null;
            displayTarget = `${githubUrl} (${branch})`;
        } else if (activeSourceType === "zip") {
            const file = zipFileInput && zipFileInput.files[0];
            if (!file) {
                alert("Please select a ZIP file to upload.");
                return;
            }
            projectName = (zipProjectNameInput && zipProjectNameInput.value.trim()) || file.name.replace(/\.zip$/i, "");
            displayTarget = `ZIP: ${file.name}`;
            zipBase64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const base64Str = reader.result.split(",")[1];
                    resolve(base64Str);
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            localPath = null;
        } else if (activeSourceType === "greenfield") {
            projectName = (greenfieldNameInput && greenfieldNameInput.value.trim()) || "new_project";
            displayTarget = `Greenfield: ${projectName}`;
            localPath = null;
        }

        isRunning = true;
        btnLaunch.disabled = true;
        btnLaunch.querySelector(".btn-text").textContent = "Executing...";
        agentStatePill.className = "status-pill state-running";
        agentStateText.textContent = mode === "multi_agent" ? "Multi-Agent Active" : "Baseline Active";

        resetPipeline();
        addTerminalLog("system", `=== Launching ${mode.toUpperCase()} on [${activeSourceType.toUpperCase()}] ${displayTarget} ===`);
        if (demoMode) {
            addTerminalLog("warning", "⚡ DEMO MODE: Simulating initial flaw to trigger self-healing & reviewer loop.");
        }

        try {
            const response = await fetch("/api/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    source_type: activeSourceType,
                    github_url: githubUrl,
                    branch: branch,
                    auth_token: authToken,
                    local_path: localPath,
                    repo_path: localPath || projectName,
                    zip_base64: zipBase64,
                    project_name: projectName,
                    isolate_local_copy: isolateLocal,
                    operator_attestation: operatorAttestationCheck ? operatorAttestationCheck.checked : false,
                    task: task,
                    max_iterations: maxIter,
                    task_type: taskType,
                    demo_mode: demoMode,
                    mode: mode,
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const jsonStr = line.slice(6).trim();
                        try {
                            const event = JSON.parse(jsonStr);
                            handleEvent(event);
                        } catch (err) {
                            console.error("Error parsing event:", err, line);
                        }
                    }
                }
            }
        } catch (err) {
            addTerminalLog("error", `Execution failed: ${err.message}`);
            pipelineStatus.textContent = "Execution Error";
        } finally {
            isRunning = false;
            btnLaunch.disabled = false;
            btnLaunch.querySelector(".btn-text").textContent = "Launch Autonomous Workflow";
            agentStatePill.className = "status-pill state-idle";
            agentStateText.textContent = "Ready";
        }
    });

    // ==========================================
    // 8. Handle SSE Events
    // ==========================================
    function handleEvent(event) {
        switch (event.type) {
            case "log":
                addTerminalLog(event.level || "info", event.message, event.timestamp);
                break;

            case "node_start":
                setNodeState(event.node, "active");
                pipelineStatus.textContent = event.label || `Executing ${event.node}`;
                if (event.inputs && nodeTraces[event.node]) {
                    nodeTraces[event.node].inputs = event.inputs;
                }
                break;

            case "node_done":
                setNodeState(event.node, "done", event.status || "Done", event.latency_ms);
                if (nodeTraces[event.node]) {
                    if (event.inputs) nodeTraces[event.node].inputs = event.inputs;
                    if (event.outputs) nodeTraces[event.node].outputs = event.outputs;
                    if (event.latency_ms !== undefined) nodeTraces[event.node].latency_ms = event.latency_ms;
                }
                break;

            case "node_skip":
                setNodeState(event.node, "skipped", "Skipped", 0);
                if (nodeTraces[event.node]) {
                    nodeTraces[event.node].status = "SKIPPED";
                    nodeTraces[event.node].inputs = event.inputs || {};
                    nodeTraces[event.node].outputs = { reason: event.reason, ...(event.outputs || {}) };
                    nodeTraces[event.node].latency_ms = 0;
                }
                addTerminalLog("system", `[LangGraph] ${event.node} skipped: ${event.reason}`);
                break;

            case "symbols_indexed":
                allSymbols = event.symbols || [];
                renderSymbols(allSymbols);
                symbolCountPill.textContent = event.count;
                break;

            case "test_results":
                updateTestResults(event);
                break;

            case "complete":
                pipelineStatus.textContent = event.passed ? "Verified Passed" : "Finished";
                renderFinalReport(event);
                break;
        }
    }

    function updateTestResults(res) {
        if (res.passed) {
            testStatusBanner.className = "test-banner passed";
            testStatusBanner.querySelector(".test-icon").textContent = "✅";
            testStatusBanner.querySelector("h4").textContent = "Pytest Passed (Exit Code 0)";
            testStatusBanner.querySelector("p").textContent = "All test assertions passed in isolated execution sandbox.";
        } else {
            testStatusBanner.className = "test-banner failed";
            testStatusBanner.querySelector(".test-icon").textContent = "❌";
            testStatusBanner.querySelector("h4").textContent = `Pytest Failed (Exit Code ${res.exit_code})`;
            testStatusBanner.querySelector("p").textContent = res.error_summary || `${res.failed_tests.length} test failure(s) detected.`;
        }

        pytestOutput.textContent = res.stdout || res.stderr || "No output returned.";
    }

    function renderFinalReport(event) {
        const gitInfo = event.git && event.git.commit_sha ? `
            <div style="background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-family: var(--font-mono); font-size: 0.8rem; color: #c7d2fe;">
                <p>🌿 <strong>Git Branch:</strong> <code>${escapeHtml(event.git.branch || 'main')}</code></p>
                <p>📦 <strong>Commit SHA:</strong> <code>${escapeHtml(event.git.commit_sha.substring(0, 10))}</code></p>
            </div>
        ` : '';

        reportContainer.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
                <h3 style="font-size: 1.2rem; font-weight: 700;">Multi-Agent Verification Report</h3>
                <span style="padding: 0.3rem 0.8rem; border-radius: 9999px; font-weight: 700; font-size: 0.8rem; ${
                    event.passed
                        ? "background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981;"
                        : "background: rgba(244, 63, 94, 0.2); color: #f87171; border: 1px solid #f43f5e;"
                }">
                    ${event.passed ? "VERIFIED PASSED" : "FAILED / ESCALATED"}
                </span>
            </div>
            ${gitInfo}
            <div style="background: #060911; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; font-family: var(--font-mono); font-size: 0.85rem;">
                <p><strong>Iterations:</strong> ${event.iterations || 0}</p>
                <p><strong>Architecture:</strong> ${event.architecture_mode === 'multi_agent' ? '5-Agent Multi-Agent Orchestration' : 'Single-Agent Baseline'}</p>
                <p><strong>Target Modules:</strong> ${event.relevant_files ? event.relevant_files.join(", ") : "None"}</p>
            </div>
            <div style="color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; font-family: var(--font-mono); font-size: 0.85rem;">
                ${event.report ? escapeHtml(event.report) : "Task execution completed successfully."}
            </div>
        `;
    }
});
