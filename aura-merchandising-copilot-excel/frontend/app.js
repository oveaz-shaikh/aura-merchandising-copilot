
const API_BASE = "http://127.0.0.1:8000";

let products = [];
let brands = [];
let deadStockData = null;

const $ = (id) => document.getElementById(id);

function showMessage(message, type = "error") {
    const element = $("global-message");
    element.textContent = message;
    element.className = `message ${type}`;
}

function clearMessage() {
    $("global-message").className = "message hidden";
    $("global-message").textContent = "";
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...options.headers
        }
    });

    const text = await response.text();
    let data;

    try {
        data = text ? JSON.parse(text) : null;
    } catch {
        data = text;
    }

    if (!response.ok) {
        const detail = data?.detail;
        const message = Array.isArray(detail)
            ? detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
            : typeof detail === "string"
                ? detail
                : `Request failed (${response.status})`;

        throw new Error(message);
    }

    return data;
}

function formatNumber(value, digits = 0) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";

    return new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: digits
    }).format(number);
}

function formatMoney(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
        return "—";
    }

    // The workbook's currency is not explicitly specified.
    return formatNumber(value, 2);
}

function safeText(value) {
    return value === null || value === undefined || value === ""
        ? "—"
        : String(value);
}

function makeCell(value) {
    const cell = document.createElement("td");
    cell.textContent = safeText(value);
    return cell;
}

function makeButton(label, callback) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-action";
    button.textContent = label;
    button.addEventListener("click", callback);
    return button;
}

function setConnectionStatus(online, message) {
    const status = $("connection-status");
    const dot = document.querySelector(".status-dot");

    status.textContent = message;
    dot.classList.toggle("online", online);
    dot.classList.toggle("offline", !online);
}

function getStock(product) {
    return Number(
        product.current_stock ??
        product.stock ??
        product.quantity ??
        0
    );
}

function renderProducts(searchTerm = "") {
    const tbody = $("products-table");
    tbody.replaceChildren();

    const query = searchTerm.trim().toLowerCase();

    const filtered = products.filter((product) => {
        const searchable = [
            product.sku,
            product.product_name,
            product.brand,
            product.brand_name
        ].filter(Boolean).join(" ").toLowerCase();

        return searchable.includes(query);
    });

    if (!filtered.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 6;
        cell.textContent = products.length
            ? "No products match your search."
            : "No products were returned by the API.";
        row.appendChild(cell);
        tbody.appendChild(row);
        return;
    }

    for (const product of filtered) {
        const row = document.createElement("tr");

        row.appendChild(makeCell(product.sku));
        row.appendChild(makeCell(product.product_name));
        row.appendChild(makeCell(product.brand || product.brand_name));
        row.appendChild(makeCell(formatMoney(product.selling_price)));
        row.appendChild(makeCell(formatNumber(getStock(product))));

        const actionCell = document.createElement("td");
        actionCell.appendChild(
            makeButton("Optimize", () => {
                $("optimizer-sku").value = product.sku;
                showSection("optimizer");
            })
        );
        row.appendChild(actionCell);

        tbody.appendChild(row);
    }
}

function populateProductSelects() {
    const selectIds = ["optimizer-sku", "forecast-sku", "marketing-sku"];

    for (const id of selectIds) {
        const select = $(id);
        select.replaceChildren();

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select a product";
        select.appendChild(placeholder);

        for (const product of products) {
            const option = document.createElement("option");
            option.value = product.sku;
            option.textContent = `${product.sku} — ${product.product_name}`;
            select.appendChild(option);
        }
    }
}

function renderOverview() {
    $("metric-products").textContent = formatNumber(products.length);

    const totalStock = products.reduce(
        (total, product) => total + getStock(product),
        0
    );
    $("metric-stock").textContent = formatNumber(totalStock);

    $("metric-brands").textContent = formatNumber(
        new Set(products.map((product) => product.brand || product.brand_id)
            .filter(Boolean)).size
    );

    const deadStockCount = Array.isArray(deadStockData)
        ? deadStockData.length
        : Array.isArray(deadStockData?.items)
            ? deadStockData.items.length
            : Array.isArray(deadStockData?.products)
                ? deadStockData.products.length
                : null;

    $("metric-deadstock").textContent =
        deadStockCount === null ? "—" : formatNumber(deadStockCount);

    renderProducts($("product-search").value);
}

async function loadProducts() {
    const data = await apiRequest("/api/products");

    if (!Array.isArray(data)) {
        throw new Error("The products endpoint did not return a list.");
    }

    products = data;
    populateProductSelects();
    renderOverview();
}

async function loadBrands() {
    const data = await apiRequest("/api/brands");
    brands = Array.isArray(data) ? data : [];
    return brands;
}

async function loadDeadStock() {
    const data = await apiRequest("/api/dead-stock");
    deadStockData = data;
    renderOverview();
    renderDeadStock(data);
    return data;
}

function showSection(sectionName) {
    const validSections = [
        "overview",
        "optimizer",
        "marketing",
        "forecast",
        "deadstock",
        "assistant"
    ];

    if (!validSections.includes(sectionName)) return;

    for (const name of validSections) {
        $(`${name}-section`).classList.toggle(
            "hidden",
            name !== sectionName
        );
    }

    document.querySelectorAll(".nav-link").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.section === sectionName
        );
    });

    const titles = {
        overview: "Overview",
        optimizer: "Promotion Optimizer",
        marketing: "Marketing Strategy",
        forecast: "Demand Forecast",
        deadstock: "Dead Stock",
        assistant: "AI Assistant"
    };

    $("page-title").textContent = titles[sectionName];
    clearMessage();
}

function addMetric(container, label, value) {
    const card = document.createElement("article");
    card.className = "result-metric";

    const heading = document.createElement("span");
    heading.textContent = label;

    const strong = document.createElement("strong");
    strong.textContent = safeText(value);

    card.append(heading, strong);
    container.appendChild(card);
}

function addTextElement(parent, tag, text, className = "") {
    const element = document.createElement(tag);
    element.textContent = safeText(text);
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
}

function renderOptimizerResult(data) {
    const container = $("optimizer-results");
    container.replaceChildren();

    const recommendation = data.recommendation || {};
    const status = data.recommendation_status || "unknown";

    const banner = document.createElement("div");
    banner.className = "result-banner";

    addTextElement(
        banner,
        "h3",
        recommendation.label || "Promotion result"
    );

    addTextElement(
        banner,
        "p",
        `${data.product_name || data.sku || ""} · ${data.brand || ""}`
    );

    const pill = document.createElement("span");
    pill.className = `status-pill ${
        status === "feasible"
            ? "good"
            : status === "no_eligible_scenario"
                ? "bad"
                : ""
    }`;
    pill.textContent = status.replaceAll("_", " ");
    banner.appendChild(pill);

    addTextElement(banner, "p", data.selection_reason || data.warning || "");
    container.appendChild(banner);

    const metrics = document.createElement("div");
    metrics.className = "result-metrics";

    addMetric(metrics, "Estimated Net Profit", formatMoney(
        recommendation.estimated_net_profit
    ));
    addMetric(metrics, "Estimated Margin", `${formatNumber(
        recommendation.estimated_margin_percent, 2
    )}%`);
    addMetric(metrics, "Expected Units Sold", formatNumber(
        recommendation.expected_units_sold
    ));
    addMetric(metrics, "Expected Revenue", formatMoney(
        recommendation.expected_revenue
    ));
    addMetric(metrics, "Stock Remaining", formatNumber(
        recommendation.expected_stock_remaining
    ));
    addMetric(metrics, "Clearance Days", formatNumber(
        recommendation.estimated_clearance_days
    ));

    container.appendChild(metrics);

    const diagnostic = document.createElement("div");
    diagnostic.className = "diagnostic-box";

    addTextElement(
        diagnostic,
        "strong",
        "Clearance diagnostic"
    );

    addTextElement(
        diagnostic,
        "p",
        data.clearance_diagnostic || data.warning || "No diagnostic provided."
    );

    addTextElement(
        diagnostic,
        "p",
        `Required daily sales: ${formatNumber(
            data.required_daily_units_to_clear_stock
        )} units · Baseline estimated clearance: ${
            data.baseline_estimated_clearance_days == null
                ? "Not estimable"
                : `${formatNumber(data.baseline_estimated_clearance_days)} days`
        } · Baseline clearance gap: ${formatNumber(
            data.clearance_gap_units
        )} units`
    );

    container.appendChild(diagnostic);

    const tableCard = document.createElement("div");
    tableCard.className = "content-card";

    addTextElement(tableCard, "h3", "Promotion Scenario Comparison");

    const wrapper = document.createElement("div");
    wrapper.className = "table-wrapper";

    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    [
        "Promotion",
        "Units",
        "Revenue",
        "Net Profit",
        "Margin",
        "Clearance Days",
        "Eligible",
        "Feasible"
    ].forEach((heading) => {
        addTextElement(headerRow, "th", heading);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    for (const scenario of data.all_scenarios || []) {
        const row = document.createElement("tr");

        [
            scenario.label,
            formatNumber(scenario.expected_units_sold),
            formatMoney(scenario.expected_revenue),
            formatMoney(scenario.estimated_net_profit),
            `${formatNumber(scenario.estimated_margin_percent, 2)}%`,
            scenario.estimated_clearance_days == null
                ? "Not estimable"
                : formatNumber(scenario.estimated_clearance_days),
            scenario.eligible ? "Yes" : "No",
            scenario.feasible ? "Yes" : "No"
        ].forEach((value) => row.appendChild(makeCell(value)));

        tbody.appendChild(row);
    }

    table.appendChild(tbody);
    wrapper.appendChild(table);
    tableCard.appendChild(wrapper);
    container.appendChild(tableCard);

    addTextElement(
        container,
        "p",
        data.methodology_note || recommendation.estimate_note || "",
        "data-note"
    );

    addTextElement(
        container,
        "p",
        "Financial figures use the workbook's numeric values. Confirm the workbook currency before treating these figures as monetary amounts.",
        "data-note"
    );
}

async function runOptimizer(event) {
    event.preventDefault();
    clearMessage();

    const sku = $("optimizer-sku").value;
    if (!sku) {
        showMessage("Select a product SKU first.");
        return;
    }

    const button = $("optimizer-form").querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Optimizing...";

    try {
        const body = {
            sku,
            deadline_days: Number($("deadline-days").value),
            objective: $("objective").value,
            minimum_margin_percent: Number($("minimum-margin").value),
            max_discount_percent: Number($("max-discount").value)
        };

        const data = await apiRequest("/api/optimize", {
            method: "POST",
            body: JSON.stringify(body)
        });

        renderOptimizerResult(data);
    } catch (error) {
        showMessage(`Optimization failed: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = "Optimize Promotions";
    }
}

function renderForecast(data) {
    const container = $("forecast-results");
    container.replaceChildren();

    const metrics = document.createElement("div");
    metrics.className = "result-metrics";

    addMetric(metrics, "Forecast Units", formatNumber(
        data.forecast_units_total ?? data.total_forecast_units
    ));
    addMetric(metrics, "Average Daily Units", formatNumber(
        data.average_forecast_units_per_day ?? data.average_daily_units,
        2
    ));
    addMetric(metrics, "Forecast Horizon", `${
        data.horizon_days ?? data.horizon_days_used ?? "—"
    } days`);

    container.appendChild(metrics);

    if (data.evaluation) {
        const evaluation = document.createElement("div");
        evaluation.className = "content-card";

        addTextElement(evaluation, "h3", "Forecast Evaluation");

        const table = document.createElement("table");
        const tbody = document.createElement("tbody");

        const fields = [
            ["Selected Method", data.selected_forecast_method || data.evaluation.selected_forecast_method],
            ["Evaluation Method", data.evaluation.method],
            ["Test Days", data.evaluation.test_days],
            ["Backtest Folds", data.evaluation.fold_count],
            ["Selected Method MAE", data.evaluation.selected_method_mae_units],
            ["Selected Method WAPE (%)", data.evaluation.selected_method_wape_percent]
        ];

        for (const [label, value] of fields) {
            const row = document.createElement("tr");
            row.appendChild(makeCell(label));
            row.appendChild(makeCell(value));
            tbody.appendChild(row);
        }

        table.appendChild(tbody);
        evaluation.appendChild(table);
        container.appendChild(evaluation);
    }

    if (Array.isArray(data.forecast)) {
        const card = document.createElement("div");
        card.className = "content-card";
        addTextElement(card, "h3", "Forecast Values");

        const wrapper = document.createElement("div");
        wrapper.className = "table-wrapper";

        const table = document.createElement("table");
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");

        ["Date", "Predicted Units"].forEach(
            (heading) => addTextElement(headRow, "th", heading)
        );

        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement("tbody");

        data.forecast.forEach((item) => {
            const row = document.createElement("tr");
            row.appendChild(makeCell(item.date || item.ds || item.day));
            row.appendChild(makeCell(
                item.predicted_units ?? item.forecast ?? item.units ?? item.yhat
            ));
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        wrapper.appendChild(table);
        card.appendChild(wrapper);
        container.appendChild(card);
    }

    if (Array.isArray(data.caveats) && data.caveats.length) {
        const note = document.createElement("div");
        note.className = "diagnostic-box";
        addTextElement(note, "strong", "Forecast limitations");

        const list = document.createElement("ul");
        data.caveats.forEach((caveat) => {
            addTextElement(list, "li", caveat);
        });

        note.appendChild(list);
        container.appendChild(note);
    }

    addTextElement(
        container,
        "p",
        data.methodology_note || "Forecast values are estimates and may not reflect actual demand.",
        "data-note"
    );
}

async function runForecast(event) {
    event.preventDefault();
    clearMessage();

    const sku = $("forecast-sku").value;
    if (!sku) {
        showMessage("Select a product SKU first.");
        return;
    }

    const button = $("forecast-form").querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = "Forecasting...";

    try {
        const horizon = Number($("forecast-horizon").value);
        const query = new URLSearchParams({
            sku,
            horizon_days: String(horizon)
        });

        const data = await apiRequest(`/api/forecast?${query.toString()}`);
        renderForecast(data);
    } catch (error) {
        showMessage(`Forecast failed: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = "Run Forecast";
    }
}

function renderDeadStock(data) {
    const container = $("deadstock-results");
    container.replaceChildren();

    const items = Array.isArray(data)
        ? data
        : data?.items || data?.products || data?.dead_stock_items || [];

    if (!items.length) {
        addTextElement(
            container,
            "div",
            typeof data === "object" && data !== null
                ? "The API returned no dead-stock item list, or no items were flagged. Review the report data below if available."
                : "No dead-stock items returned.",
            "empty-state"
        );

        if (data && !Array.isArray(data)) {
            const details = document.createElement("pre");
            details.className = "data-note";
            details.style.whiteSpace = "pre-wrap";
            details.textContent = JSON.stringify(data, null, 2);
            container.appendChild(details);
        }
        return;
    }

    const card = document.createElement("div");
    card.className = "content-card";

    const wrapper = document.createElement("div");
    wrapper.className = "table-wrapper";

    const table = document.createElement("table");
    const keys = [...new Set(items.flatMap((item) => Object.keys(item)))];
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    keys.slice(0, 8).forEach((key) => {
        addTextElement(headerRow, "th", key.replaceAll("_", " "));
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    items.forEach((item) => {
        const row = document.createElement("tr");

        keys.slice(0, 8).forEach((key) => {
            row.appendChild(makeCell(
                typeof item[key] === "object"
                    ? JSON.stringify(item[key])
                    : item[key]
            ));
        });

        tbody.appendChild(row);
    });

    table.appendChild(tbody);
    wrapper.appendChild(table);
    card.appendChild(wrapper);
    container.appendChild(card);
}

function escapeHTML(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

// Render the common Markdown formats returned by the AI as safe chat HTML.
function formatChatAnswer(markdown) {
    const lines = escapeHTML(markdown).replace(/\r\n?/g, "\n").split("\n");
    const output = [];
    let paragraph = [];
    let listItems = [];
    let tableRows = [];

    const inlineFormat = (text) => text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
    const flushParagraph = () => {
        if (paragraph.length) {
            output.push(`<p>${inlineFormat(paragraph.join("<br>"))}</p>`);
            paragraph = [];
        }
    };
    const flushList = () => {
        if (listItems.length) {
            output.push(`<ul>${listItems.map((item) => `<li>${inlineFormat(item)}</li>`).join("")}</ul>`);
            listItems = [];
        }
    };
    const flushTable = () => {
        if (tableRows.length) {
            const rows = tableRows.filter((line) => !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line));
            if (rows.length) {
                const cells = rows.map((line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()));
                const header = cells[0] || [];
                const body = cells.slice(1);
                output.push(`<div class="chat-table-wrapper"><table><thead><tr>${header.map((cell) => `<th>${inlineFormat(cell)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${header.map((_, index) => `<td>${inlineFormat(row[index] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
            }
            tableRows = [];
        }
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
            flushParagraph(); flushList(); flushTable();
            continue;
        }
        if (trimmed.includes("|") && /^\|?.+\|.+\|?$/.test(trimmed)) {
            flushParagraph(); flushList();
            tableRows.push(trimmed);
            continue;
        }
        flushTable();
        const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
            flushParagraph(); flushList();
            const level = heading[1].length + 2;
            output.push(`<h${level}>${inlineFormat(heading[2])}</h${level}>`);
        } else if (/^[-*]\s+/.test(trimmed)) {
            flushParagraph();
            listItems.push(trimmed.replace(/^[-*]\s+/, ""));
        } else if (/^\d+[.)]\s+/.test(trimmed)) {
            flushParagraph();
            listItems.push(trimmed.replace(/^\d+[.)]\s+/, ""));
        } else {
            flushList();
            paragraph.push(trimmed);
        }
    }
    flushParagraph(); flushList(); flushTable();
    return output.join("");
}

function addChatMessage(message, sender) {
    const container = $("chat-messages");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;
    if (sender === "assistant") {
        bubble.innerHTML = formatChatAnswer(message);
    } else {
        bubble.textContent = message;
    }
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return bubble;
}


async function generateMarketingPlan(event) {
    event.preventDefault();
    clearMessage();

    const sku = $("marketing-sku").value;
    if (!sku) {
        showMessage("Select a product SKU first.");
        return;
    }

    const button = $("marketing-form").querySelector('button[type="submit"]');
    const results = $("marketing-results");
    button.disabled = true;
    button.textContent = "Generating plan...";
    results.replaceChildren();
    addTextElement(results, "div", "Building a grounded marketing plan...", "empty-state");

    const deadline = Number($("marketing-deadline").value);
    const objective = $("marketing-objective").value;
    const targetRaw = $("marketing-target-units").value.trim();
    const targetUnits = targetRaw ? Number(targetRaw) : null;
    const objectiveText = {
        balanced: "balance sales and profit",
        clearance: "clear stock as quickly as practical while respecting optimizer constraints",
        profit: "prioritize profit while still proposing a useful campaign"
    }[objective];
    const message = `Create a practical marketing strategy for SKU ${sku} for a ${deadline}-day campaign. Objective: ${objectiveText}. Include: (1) verified product and inventory snapshot, (2) target audience only where supported by the available data and clearly label assumptions, (3) campaign concept and value proposition, (4) suggested channels and why, (5) a phased weekly/day-range calendar, (6) promotion and discount recommendation based only on the supplied Python optimizer result, (7) KPIs and how to measure them, and (8) risks, assumptions, and missing data. Do not invent customer demographics, marketing budget, campaign performance, or promotion uplift. Clearly distinguish recommendations from facts. No campaign should be executed. ${targetUnits ? `Target ${targetUnits} units if the available stock and optimizer context support it.` : "Use available stock as the planning context."}`;

    try {
        const body = { message, sku, deadline_days: deadline, objective, ...(targetUnits ? { target_units: targetUnits } : {}) };
        const data = await apiRequest("/api/chat", {
            method: "POST",
            body: JSON.stringify(body)
        });
        const answer = typeof data === "string" ? data : data.answer || data.response || data.message || JSON.stringify(data, null, 2);
        results.replaceChildren();
        const card = document.createElement("div");
        card.className = "content-card marketing-answer";
        const heading = document.createElement("h3");
        heading.textContent = `Marketing Plan — ${sku}`;
        const answerEl = document.createElement("div");
        answerEl.className = "chat-bubble assistant";
        answerEl.innerHTML = formatChatAnswer(answer);
        card.append(heading, answerEl);
        results.appendChild(card);
        addTextElement(results, "p", "Note: recommendations are AI-generated from the context returned by the application. Confirm financial figures and campaign assumptions before acting. No campaign was executed.", "data-note");
    } catch (error) {
        results.replaceChildren();
        addTextElement(results, "div", `Marketing plan generation failed: ${error.message}`, "empty-state");
    } finally {
        button.disabled = false;
        button.textContent = "Generate Marketing Plan";
    }
}

async function sendChatMessage(event) {
    event.preventDefault();
    clearMessage();

    const input = $("chat-input");
    const message = input.value.trim();

    if (!message) return;

    addChatMessage(message, "user");
    input.value = "";

    const waiting = addChatMessage("Thinking...", "assistant");
    const button = $("chat-form").querySelector('button[type="submit"]');
    button.disabled = true;

    try {
        const body = {
            message,
            deadline_days: Number($("deadline-days").value) || 30,
            objective: $("objective").value || "balanced"
        };

        const data = await apiRequest("/api/chat", {
            method: "POST",
            body: JSON.stringify(body)
        });

        const answer = typeof data === "string"
            ? data
            : data.answer || data.response || data.message ||
              JSON.stringify(data, null, 2);
        waiting.innerHTML = formatChatAnswer(answer);
    } catch (error) {
        waiting.textContent = `Sorry, the request failed: ${error.message}`;
    } finally {
        button.disabled = false;
        input.focus();
    }
}

async function refreshDashboard() {
    clearMessage();
    setConnectionStatus(false, "Connecting...");

    try {
        await apiRequest("/health");
        setConnectionStatus(true, "Connected");

        await loadProducts();

        try {
            await loadBrands();
        } catch (error) {
            console.warn("Brands endpoint unavailable:", error.message);
            brands = [];
        }

        try {
            await loadDeadStock();
        } catch (error) {
            console.warn("Dead-stock endpoint unavailable:", error.message);
            $("metric-deadstock").textContent = "—";
        }
    } catch (error) {
        setConnectionStatus(false, "Disconnected");
        showMessage(
            `Could not load dashboard data: ${error.message}. Make sure FastAPI is running at ${API_BASE}.`
        );
    }
}

document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => {
        showSection(button.dataset.section);
    });
});

$("refresh-button").addEventListener("click", refreshDashboard);

$("product-search").addEventListener("input", (event) => {
    renderProducts(event.target.value);
});

$("optimizer-form").addEventListener("submit", runOptimizer);
$("marketing-form").addEventListener("submit", generateMarketingPlan);
$("forecast-form").addEventListener("submit", runForecast);
$("deadstock-refresh").addEventListener("click", async () => {
    const button = $("deadstock-refresh");
    button.disabled = true;
    button.textContent = "Loading...";

    try {
        await loadDeadStock();
    } catch (error) {
        showMessage(`Could not load dead-stock report: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = "Load Report";
    }
});

$("chat-form").addEventListener("submit", sendChatMessage);

refreshDashboard();
