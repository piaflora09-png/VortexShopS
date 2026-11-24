const title = document.querySelector("#verificationTitle");
const message = document.querySelector("#verificationMessage");

function showFailure(text) {
  title.textContent = "Verification unavailable";
  message.textContent = text;
}

async function loadVerification() {
  try {
    const response = await fetch("/auth/status");
    if (!response.ok) throw new Error("Could not check your session. Please try again.");
    const data = await response.json();
    if (!data.authenticated) {
      window.location.replace("/");
      return;
    }
    if (!data.verification?.verified) {
      showFailure("Your account is not marked as verified. Please sign in again or contact server staff.");
      return;
    }

    title.textContent = "Verification complete";
    message.textContent = "Your Discord account is verified in the Vortex community.";
    document.querySelector("#discordUsername").textContent = data.user.username;
    document.querySelector("#discordId").textContent = data.user.id;
    const date = new Date(data.verification.verified_at);
    document.querySelector("#verifiedAt").textContent =
      Number.isNaN(date.getTime()) ? "Recorded" : date.toLocaleString();
    document.querySelector("#verificationDetails").hidden = false;
  } catch (error) {
    showFailure(error.message);
  }
}

document.querySelector("#logout").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/auth/logout", { method: "POST" });
    if (!response.ok) throw new Error("Could not log out. Please try again.");
    window.location.replace("/");
  } catch (error) {
    button.disabled = false;
    message.textContent = error.message;
  }
});

loadVerification();
