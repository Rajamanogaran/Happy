const form = document.querySelector("#login-form");
form.onsubmit = async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password: document.querySelector("#password").value,
      }),
    });
    const data = await response.json();
    if (!response.ok)
      throw Error(
        typeof data.detail === "string" ? data.detail : "Unable to sign in.",
      );
    location.replace("/");
  } catch (error) {
    document.querySelector("#login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
fetch("/auth/status")
  .then((r) => r.json())
  .then((s) => {
    if (s.authenticated) location.replace("/");
  })
  .catch(() => {});
