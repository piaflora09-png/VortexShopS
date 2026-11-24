const labels = {
  overview: "Command Center",
  security: "Security activity",
  moderation: "Moderation history",
  tickets: "Support tickets",
  "ticket-panel": "Ticket Panel Editor",
  campaigns: "Campaign history",
  giveaways: "Giveaway history",
  transactions: "Transactions",
};

async function loadStatus() {
  const response = await fetch("/auth/status");
  if (!response.ok) throw new Error("Could not check your login session.");
  const data = await response.json();
  if (!data.authenticated) {
    window.location.replace("/");
    return false;
  }
  window.vortexCsrfToken = data.csrf_token;
  return true;
}

async function loadOverview() {
  const response = await fetch("/api/overview");
  if (response.status === 401) { window.location.replace("/"); return; }
  if (!response.ok) {
    if (response.status === 403) throw new Error("This dashboard is limited to configured staff.");
    throw new Error("Dashboard data could not be loaded.");
  }
  const data = await response.json();
  document.querySelector("#botStatus").textContent = data.bot_status;
  document.querySelector("#botStatus").className = `status ${data.bot_status === "online" ? "online" : "offline"}`;
  document.querySelector("#verified").textContent = data.verified;
  document.querySelector("#moderationCount").textContent = data.moderation;
  document.querySelector("#ticketsCount").textContent = data.open_tickets;
  document.querySelector("#securityCount").textContent = data.security_events;
  const activity = document.querySelector("#activity");
  activity.replaceChildren();
  if (!data.recent_activity.length) {
    activity.append(makeMessage("No security events have been recorded."));
    return;
  }
  for (const item of data.recent_activity) {
    const row = document.createElement("div");
    row.className = "activity-row";
    const title = document.createElement("strong");
    title.textContent = item.event_type;
    const date = document.createElement("small");
    date.textContent = formatDate(item.created_at);
    row.append(title, date);
    activity.append(row);
  }
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value ?? "") : date.toLocaleString();
}

function makeMessage(text, className = "empty-state") {
  const message = document.createElement("p");
  message.className = className;
  message.textContent = text;
  return message;
}

async function showView(view) {
  document.querySelectorAll(".nav-item").forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  document.querySelector("#pageTitle").textContent = labels[view] ?? "Dashboard";
  document.querySelector("#overviewView").hidden = view !== "overview";
  document.querySelector("#recordsView").hidden = view === "overview" || view === "ticket-panel";
  document.querySelector("#ticketPanelView").hidden = view !== "ticket-panel";
  if (view === "ticket-panel") {
    await loadTicketPanelSettings();
    return;
  }
  if (view === "overview") return;

  const records = document.querySelector("#records");
  records.replaceChildren(makeMessage("Loading…"));
  const description = document.querySelector("#sectionDescription");
  description.textContent = view === "transactions"
    ? "Recorded transactions only. The $50,000 daily figure is a target, not actual revenue."
    : "Recent records from this server. This view is read-only.";
  try {
    const endpoint = view === "transactions"
      ? "/api/transaction-history"
      : `/api/records/${encodeURIComponent(view)}`;
    const response = await fetch(endpoint);
    if (response.status === 401) { window.location.replace("/"); return; }
    if (!response.ok) {
      if (response.status === 403) throw new Error("This section is limited to configured staff.");
      throw new Error("Could not load these records. Try again.");
    }
    const result = await response.json();
    records.replaceChildren();
    if (!result.items.length) {
      records.append(makeMessage("No records yet."));
      return;
    }
    for (const item of result.items) {
      const card = document.createElement("article");
      card.className = "record";
      const heading = document.createElement("strong");
      heading.textContent = item.event_type ?? item.action ?? item.name
        ?? item.prize ?? item.category ?? item.description ?? item.status ?? "Record";
      const detail = document.createElement("span");
      detail.textContent = view === "transactions"
        ? `${(item.amount_cents / 100).toFixed(2)} ${item.currency} · ${item.status}`
        : [item.status, item.reason, item.prize_type].filter(Boolean).join(" · ");
      const date = document.createElement("small");
      date.textContent = formatDate(item.created_at ?? item.ends_at);
      card.append(heading, detail, date);
      records.append(card);
    }
  } catch (error) {
    records.replaceChildren(makeMessage(error.message, "error-state"));
  }
}

async function loadTicketPanelSettings() {
  const message = document.querySelector("#ticketPanelMessage");
  message.textContent = "Loading ticket panel settings…";
  try {
    const response = await fetch("/api/ticket-panel");
    if (response.status === 401) { window.location.replace("/"); return; }
    if (!response.ok) {
      if (response.status === 403) throw new Error("Ticket panel settings are limited to configured staff.");
      throw new Error("Could not load ticket panel settings.");
    }
    const data = await response.json();
    document.querySelector("#panelTitle").value = data.title;
    document.querySelector("#panelDescription").value = data.description;
    document.querySelector("#panelCategories").value = data.categories.join("; ");
    const channelSelect = document.querySelector("#panelChannel");
    channelSelect.replaceChildren(new Option("Select a channel", ""));
    for (const channel of data.channels) {
      channelSelect.add(new Option(`#${channel.name}`, channel.id));
    }
    channelSelect.value = data.panel_channel_id;
    message.textContent = data.panel_message_id
      ? "Existing panel loaded. Save to update it."
      : "No panel has been published yet.";
  } catch (error) {
    message.textContent = error.message;
  }
}

document.querySelector("#ticketPanelForm")?.addEventListener("submit", async event => {
  event.preventDefault();
  const button = document.querySelector("#saveTicketPanel");
  const message = document.querySelector("#ticketPanelMessage");
  button.disabled = true;
  message.textContent = "Publishing panel…";
  try {
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/ticket-panel", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": window.vortexCsrfToken ?? "",
      },
      body: JSON.stringify(Object.fromEntries(form.entries())),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message ?? result.error ?? "Could not publish panel.");
    message.textContent = `Panel published or updated. Open it: ${result.message_url}`;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#logout")?.addEventListener("click", async () => {
  const button = document.querySelector("#logout");
  button.disabled = true;
  try {
    const response = await fetch("/auth/logout", { method: "POST" });
    if (!response.ok) throw new Error("Could not log out. Please try again.");
    window.location.replace("/");
  } catch (error) {
    button.disabled = false;
    window.alert(error.message);
  }
});

document.querySelectorAll(".nav-item").forEach(button => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

loadStatus().then(authenticated => {
  if (authenticated) return loadOverview();
}).catch(error => {
  document.querySelector("#activity").replaceChildren(makeMessage(error.message, "error-state"));
});
