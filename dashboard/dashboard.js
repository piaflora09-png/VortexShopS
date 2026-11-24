const labels = {
  overview: "Command Center",
  security: "Security activity",
  moderation: "Moderation history",
  tickets: "Support tickets",
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
  document.querySelector("#recordsView").hidden = view === "overview";
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
