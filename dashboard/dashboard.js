let csrfToken = "";

async function loadStatus() {
  const response = await fetch("/auth/status");
  if (!response.ok || !(await response.clone().json()).authenticated) {
    window.location.assign("/");
  }
}

async function loadOverview() {
  const response = await fetch("/api/overview");
  if (response.status === 401) { window.location.assign("/"); return; }
  if (!response.ok) { throw new Error("Overview unavailable"); }
  const data = await response.json();
  document.querySelector("#botStatus").textContent = data.bot_status;
  document.querySelector("#botStatus").className = `status ${data.bot_status}`;
  document.querySelector("#verified").textContent = data.verified;
  document.querySelector("#moderation").textContent = data.moderation;
  document.querySelector("#tickets").textContent = data.open_tickets;
  document.querySelector("#securityCount").textContent = data.security_events;
  document.querySelector("#activity").innerHTML = data.recent_activity.length
    ? data.recent_activity.map(item =>
        `<div class="activity-row"><strong>${escapeHtml(item.event_type)}</strong>
         <small>${escapeHtml(item.created_at)}</small></div>`).join("")
    : "<p>No security events recorded.</p>";
}

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = value ?? "";
  return element.innerHTML;
}

document.querySelector("#logout")?.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.assign("/");
});

loadStatus().then(loadOverview).catch(() => {
  document.querySelector("#activity").textContent = "Unable to load dashboard data.";
});
