console.log("Inbox2Done extension loaded in Gmail");

function getOpenEmailText() {
  const messageBodies = document.querySelectorAll('div[role="listitem"] .a3s');

  if (messageBodies.length === 0) {
    return "";
  }

  const latestMessage = messageBodies[messageBodies.length - 1];
  return latestMessage.innerText.trim();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function createPanel() {
  if (document.getElementById("inbox2done-panel")) {
    return;
  }

  const panel = document.createElement("div");
  panel.id = "inbox2done-panel";

  panel.innerHTML = `
    <div class="inbox2done-header">
      <strong>Inbox2Done</strong>
      <button id="inbox2done-close">×</button>
    </div>

    <button id="inbox2done-analyze-current">
      Summarize Open Email
    </button>

    <button id="inbox2done-analyze-today">
      Summarize Today’s Emails
    </button>

    <div id="inbox2done-result">
      Choose an option above.
    </div>
  `;

  document.body.appendChild(panel);

  document
    .getElementById("inbox2done-close")
    .addEventListener("click", () => panel.remove());

  document
    .getElementById("inbox2done-analyze-current")
    .addEventListener("click", analyzeCurrentEmail);

  document
    .getElementById("inbox2done-analyze-today")
    .addEventListener("click", analyzeToday);
}

async function analyzeCurrentEmail() {
  const result = document.getElementById("inbox2done-result");
  const emailText = getOpenEmailText();

  if (!emailText) {
    result.textContent =
      "No open email found. Open a Gmail message and try again.";
    return;
  }

  result.textContent = "Analyzing open email...";

  try {
    const response = await fetch("http://localhost:4000/analyze-email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ emailText }),
    });

    if (!response.ok) {
      throw new Error("Failed to analyze email");
    }

    const analysis = await response.json();

    const actions = analysis.recommendedActions
      .map((action) => `<li>${escapeHtml(action)}</li>`)
      .join("");

    const deadlines =
      analysis.deadlines.length > 0
        ? analysis.deadlines
            .map((deadline) => `<li>${escapeHtml(deadline)}</li>`)
            .join("")
        : "<li>No deadlines found</li>";

    result.innerHTML = `
      <h3>Summary</h3>
      <p>${escapeHtml(analysis.summary)}</p>

      <h3>Priority</h3>
      <p>${escapeHtml(analysis.priority)}</p>

      <h3>Recommended Actions</h3>
      <ul>${actions}</ul>

      <h3>Deadlines</h3>
      <ul>${deadlines}</ul>

      ${
        analysis.suggestedReply
          ? `
            <h3>Suggested Reply</h3>
            <div class="inbox2done-reply">
              ${escapeHtml(analysis.suggestedReply)}
            </div>
          `
          : ""
      }
    `;
  } catch (error) {
    console.error(error);
    result.textContent =
      "Could not analyze the open email. Make sure the backend is running.";
  }
}

async function analyzeToday() {
  const result = document.getElementById("inbox2done-result");

  result.textContent = "Building today’s email brief...";

  try {
    const response = await fetch(
      "http://localhost:4000/gmail/daily-summary"
    );

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.error || "Failed to generate daily summary");
    }

    const summary = await response.json();

    const urgentItems =
      summary.urgentItems.length > 0
        ? summary.urgentItems
            .map(
              (item) => `
                <li>
                  <strong>${escapeHtml(item.subject)}</strong><br>
                  ${escapeHtml(item.reason)}
                </li>
              `
            )
            .join("")
        : "<li>No urgent items</li>";

    const actions =
      summary.recommendedActions.length > 0
        ? summary.recommendedActions
            .map(
              (item) => `
                <li>
                  ${escapeHtml(item.action)}
                  ${
                    item.relatedSubject
                      ? `<br><small>${escapeHtml(
                          item.relatedSubject
                        )}</small>`
                      : ""
                  }
                </li>
              `
            )
            .join("")
        : "<li>No recommended actions</li>";

    const deadlines =
      summary.deadlines.length > 0
        ? summary.deadlines
            .map(
              (item) => `
                <li>
                  <strong>${escapeHtml(item.deadline)}</strong>
                  ${
                    item.relatedSubject
                      ? `<br><small>${escapeHtml(
                          item.relatedSubject
                        )}</small>`
                      : ""
                  }
                </li>
              `
            )
            .join("")
        : "<li>No deadlines found</li>";

    const emails =
      summary.emails.length > 0
        ? summary.emails
            .map(
              (email) => `
                <div class="inbox2done-email-card">
                  <strong>${escapeHtml(email.subject)}</strong>
                  <div>${escapeHtml(email.sender)}</div>
                  <p>${escapeHtml(email.summary)}</p>
                  <div>
                    Priority: ${escapeHtml(email.priority)}
                  </div>
                  <div>
                    Recommendation: ${escapeHtml(email.recommendation)}
                  </div>
                </div>
              `
            )
            .join("")
        : "<p>No emails found for today.</p>";

    result.innerHTML = `
      <h3>Today’s Overview</h3>
      <p>${escapeHtml(summary.overview)}</p>

      <h3>Urgent Items</h3>
      <ul>${urgentItems}</ul>

      <h3>Recommended Actions</h3>
      <ul>${actions}</ul>

      <h3>Deadlines</h3>
      <ul>${deadlines}</ul>

      <h3>Email Breakdown</h3>
      ${emails}
    `;
  } catch (error) {
    console.error(error);
    result.textContent =
      "Could not generate today’s summary. Reconnect Gmail and make sure the backend is running.";
  }
}

createPanel();