"use strict";

const el = (id) => document.getElementById(id);
const accountText = {checking: "Vérification…", connected: "Connecté", required: "Connexion requise", unknown: "Indisponible"};
const mqttText = {waiting: "Connexion…", online: "Connecté", offline: "Hors ligne", disabled: "Désactivée"};
const loginText = {
  failed: "Connexion interrompue. Vérifie que la connexion par code est autorisée dans les paramètres de Codex.",
  expired: "Le code a expiré. Lance une nouvelle connexion.",
  cancelled: "Connexion annulée.",
  connected: "Connexion confirmée par OpenAI."
};
const formatter = new Intl.DateTimeFormat("fr-FR", {dateStyle: "short", timeStyle: "short"});
const percent = new Intl.NumberFormat("fr-FR", {maximumFractionDigits: 1});
let csrf = "";
let pending = false;
let next;

function date(epoch) {
  return formatter.format(new Date(epoch * 1000));
}

function renderWindow(key, window, stale, known) {
  const meter = el(key + "-meter");
  const value = window?.remaining;
  el(key + "-value").textContent = value == null ? "—" : percent.format(value) + " %";
  meter.hidden = value == null;
  if (value != null) meter.value = value;
  let text = known ? "Fenêtre indisponible" : "";
  if (window) text = window.reset_at ? "Recharge le " + date(window.reset_at) : "Recharge inconnue";
  el(key + "-reset").textContent = stale && window ? "Relevé périmé · " + text : text;
}

function render(state) {
  csrf = state.csrf;
  el("account").textContent = accountText[state.auth] ?? "Indisponible";
  el("mqtt").textContent = mqttText[state.mqtt] ?? "Indisponible";
  el("observed").textContent = state.observed_at ? date(state.observed_at) : "—";
  const minutes = state.page?.short?.minutes;
  el("short-label").textContent = minutes === 300 ? "Fenêtre 5 h" : minutes === 1440 ? "Fenêtre 24 h" : "Fenêtre courte";
  renderWindow("short", state.page?.short, state.stale, !!state.page);
  renderWindow("week", state.page?.week, state.stale, !!state.page);
  el("connect").textContent = state.auth === "connected" ? "Reconnecter mon compte ChatGPT" : "Connecter mon compte ChatGPT";
  el("connect").disabled = state.busy;
  el("probe").disabled = state.auth !== "connected";
  el("device").hidden = !state.device;
  el("code").textContent = state.device?.code ?? "";
  if (state.device) {
    el("deadline").textContent = "Valable jusqu’au " + date(state.device.deadline) + ".";
    el("verification").href = state.device.url;
  }
  let status = "";
  if (state.source === "error") status = "Lecture indisponible. Réessaie dans un instant.";
  else if (state.stale) status = "Le dernier relevé est périmé.";
  else if (state.source === "ok") status = "Dernière lecture réussie.";
  if (state.busy && !state.device) status = "Un autre administrateur a déjà démarré une connexion.";
  if (state.device) status = "En attente de ta confirmation chez OpenAI.";
  if (state.login && (!status || state.login !== "connected")) status = loginText[state.login] ?? status;
  if (state.action_error === "busy") status = "Une connexion est déjà en cours.";
  el("feedback").textContent = status;
}

async function refresh(action) {
  if (pending) return;
  clearTimeout(next);
  pending = true;
  for (const name of ["connect", "probe", "cancel"]) el(name).disabled = true;
  if (action) el("feedback").textContent = "Demande en cours…";
  try {
    const response = await fetch("./api/" + (action ?? "state"),
      action ? {method: "POST", headers: {"X-Mission-CSRF": csrf}} : {});
    if (!response.ok) throw new Error("Panel unavailable");
    render(await response.json());
  } catch {
    el("feedback").textContent = "Le panneau ne répond pas. Rouvre-le depuis Home Assistant si cela persiste.";
    el("device").hidden = true;
    el("code").textContent = "";
  } finally {
    pending = false;
    el("cancel").disabled = false;
    next = setTimeout(refresh, el("device").hidden ? 8000 : 1800);
  }
}

for (const name of ["connect", "probe", "cancel"]) {
  el(name).addEventListener("click", () => refresh(name));
}
el("copy").addEventListener("click", async () => {
  const code = el("code");
  try {
    await navigator.clipboard.writeText(code.textContent);
    el("feedback").textContent = "Code copié.";
  } catch {
    const range = document.createRange();
    range.selectNodeContents(code);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    code.focus();
  }
});
refresh();
