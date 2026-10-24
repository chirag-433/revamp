(function () {
  const root = document.querySelector("[data-helpdesk]");
  if (!root) return;
  const panel = root.querySelector("[data-helpdesk-panel]");
  const input = root.querySelector("[data-helpdesk-input]");
  const form = root.querySelector("[data-helpdesk-form]");
  const messages = root.querySelector("[data-helpdesk-messages]");
  const csrf = form?.querySelector("input[name=csrfmiddlewaretoken]")?.value || "";

  root.querySelector("[data-helpdesk-open]").addEventListener("click", function () {
    if (panel.hidden) {
      panel.hidden = false;
      input.focus();
    } else {
      panel.hidden = true;
    }
  });
  root.querySelector("[data-helpdesk-close]").addEventListener("click", function () {
    panel.hidden = true;
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    addMessage(message, "user");
    input.value = "";
    input.disabled = true;
    form.querySelector("button").disabled = true;
    const pending = addMessage("Thinking...", "assistant pending");
    try {
      const response = await fetch("/api/ai-helpdesk/", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
        body: JSON.stringify({message: message})
      });
      const data = await response.json();
      pending.textContent = data.answer || data.error || "I could not answer that right now.";
      pending.classList.remove("pending");
    } catch (error) {
      pending.textContent = "I could not connect right now. Please try again.";
      pending.classList.remove("pending");
    } finally {
      input.disabled = false;
      form.querySelector("button").disabled = false;
      input.focus();
    }
  });

  function addMessage(text, className) {
    const message = document.createElement("div");
    message.className = "helpdesk-message " + className;
    message.textContent = text;
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
    return message;
  }
}());
