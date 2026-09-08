// Vitalytics — frontendlogica (vanilla JS, geen externe CDN's)
const $ = (sel) => document.querySelector(sel);

/* demo-modus (account 'demo'): alleen bekijken. De server weigert alle
   mutaties (403); dit vangt klikken af zodat ook niets visueel reageert. */
const DEMO = document.body.classList.contains("demo");
if (DEMO) {
  document.addEventListener("click", (e) => {
    if (e.target.closest("button")) {
      e.preventDefault();
      e.stopPropagation();
    }
  }, true);
}

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  let data = {};
  try { data = await res.json(); } catch (e) { /* geen json-body */ }
  if (!res.ok) throw new Error(data.error || res.statusText || "Onbekende fout");
  return data;
}

/* ---------------- zacht binnenkomen van blokken ---------------- */
function initReveal() {
  const els = document.querySelectorAll("[data-reveal]");
  if (!els.length) return;
  const reduce = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("revealed"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("revealed");
      io.unobserve(entry.target);
    });
  }, { threshold: 0.06, rootMargin: "0px 0px -24px 0px" });
  els.forEach((el) => io.observe(el));
}

/* ---------------- snackbar (M3) ---------------- */
let snackTimer;
function toast(msg, ok = true) {
  const el = $("#snackbar");
  if (!el) return;
  el.textContent = msg;
  el.className = "snackbar show" + (ok ? "" : " err");
  clearTimeout(snackTimer);
  snackTimer = setTimeout(() => { el.className = "snackbar"; }, 4000);
}

function busy(btn, on, label) {
  if (!btn) return;
  btn.disabled = on;
  if (on) {
    btn.dataset.orig = btn.innerHTML; // innerHTML: icoontjes (sparkles) blijven behouden
    btn.textContent = label || "Bezig…";
  } else if (btn.dataset.orig) {
    btn.innerHTML = btn.dataset.orig;
  }
}

/* ---------------- sparklines (inline SVG, geen libraries) ---------------- */
function fmtNum(v) {
  return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("nl-NL")
                             : Math.round(v * 10) / 10;
}

function sparkSvg(values, unit) {
  const w = 240, h = 46, pad = 5;
  const min = Math.min(...values), max = Math.max(...values);
  const span = (max - min) || 1;
  const pts = values.map((v, i) => {
    const x = pad + (i * (w - 2 * pad)) / (values.length - 1);
    const y = h - pad - ((v - min) / span) * (h - 2 * pad);
    return [x.toFixed(1), y.toFixed(1)];
  });
  const lastPt = pts[pts.length - 1];
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img">
    <polyline points="${pts.map((p) => p.join(",")).join(" ")}" fill="none"
      stroke="var(--primary)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${lastPt[0]}" cy="${lastPt[1]}" r="3.5" fill="var(--tertiary)"/>
  </svg>
  <div class="spark-range"><span>${fmtNum(min)}</span><span>${fmtNum(max)} ${unit}</span></div>`;
}

function drawSparks() {
  document.querySelectorAll(".spark[data-spark]").forEach((el) => {
    const vals = el.dataset.spark.split(",").map(Number)
      .filter((v) => !Number.isNaN(v));
    if (vals.length < 2) return;
    el.innerHTML = sparkSvg(vals, el.dataset.unit || "");
  });
}

/* ---------------- systeemstatus in de drawer ---------------- */
async function loadStatus() {
  const box = $("#drawer-status");
  if (!box) return;
  const row = (ok, label) =>
    `<div class="foot-row"><span class="dot ${ok ? "ok" : "err"}"></span>${label}</div>`;
  try {
    const h = await api("/api/health");
    box.innerHTML =
      row(true, "SQLite actief") +
      row(h.garmin_lib, h.garmin_lib ? "garminconnect gereed"
                                     : "geen garminconnect — CSV/demo werken wel");
  } catch (e) {
    box.innerHTML = row(false, e.message);
  }
}

/* ---------------- dashboard ---------------- */
function initDashboard() {
  const sync = $("#btn-sync");
  sync?.addEventListener("click", async () => {
    busy(sync, true, "Syncen…");
    try {
      const r = await api("/api/garmin/sync", { method: "POST" });
      toast(`Sync voltooid: ${r.dagen} dag(en) geïmporteerd`);
      setTimeout(() => location.reload(), 900);
    } catch (e) { toast(e.message, false); busy(sync, false); }
  });

  if (!sync || DEMO) return; // automatische sync alleen op het dashboard, niet in demo

  /* automatisch synchroniseren zodra de pagina voor het eerst in een half uur
     wordt geopend — de server beslist (throttle) of er echt gesynct wordt */
  busy(sync, true, "Syncen…");
  api("/api/garmin/auto-sync", { method: "POST" })
    .then((r) => {
      busy(sync, false);
      if (r.gesynced) {
        toast(`Automatisch gesynchroniseerd: ${r.dagen} dag(en) + ${r.activiteiten} activiteit(en)`);
        setTimeout(() => location.reload(), 1200);
      }
    })
    .catch(() => busy(sync, false));
}

/* ---------------- advies ---------------- */
function initAdvice() {
  const aiBtn = $("#btn-advice-ai");
  const rulesBtn = $("#btn-advice-rules");
  const status = $("#advice-status");
  const config = $("#ai-config");
  let running = false;

  fetch("/api/health").then((r) => r.json()).then((h) => {
    if (!config) return;
    if (h.ai_api) {
      config.textContent = `AI via ${h.ai_bron} \u2014 let op: je gezondheidsdata gaat hiervoor via de cloud.`;
      aiBtn?.removeAttribute("disabled");
      return;
    }
    if (!h.ollama) {
      config.textContent = "AI niet beschikbaar (Ollama draait niet en er is geen API ingesteld) — de regelengine werkt altijd.";
      aiBtn?.setAttribute("disabled", "");
      if (aiBtn) aiBtn.title = "Start Ollama of stel een API in bij Instellingen";
    } else if (h.model_advice === "uit") {
      config.textContent = "AI staat uit in Instellingen — de AI-knop is vergrendeld.";
      aiBtn?.setAttribute("disabled", "");
    } else {
      const model = h.model_advice === "auto" ? `automatisch (${h.models[0]})` : h.model_advice;
      config.textContent = `AI-model: ${model} — draait volledig lokaal via Ollama.`;
      aiBtn?.removeAttribute("disabled");
    }
  }).catch(() => {});

  async function run(mode, btn, busyLabel) {
    if (running) { toast("Er loopt al een analyse — even geduld", false); return; }
    running = true;
    busy(btn, true, busyLabel);
    const other = mode === "ai" ? rulesBtn : aiBtn;
    other?.setAttribute("disabled", "");
    if (status) status.textContent = mode === "ai"
      ? "De AI analyseert je metingen, activiteiten en maaltijden — dit kan tot enkele minuten duren…"
      : "De regelengine berekent je advies…";
    try {
      const r = await api("/api/advice/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      toast(`${r.source}: readyheid ${r.readiness}`);
      setTimeout(() => location.reload(), 1100);
    } catch (e) {
      toast(e.message, false);
      if (status) status.textContent = "";
      busy(btn, false);
      other?.removeAttribute("disabled");
      running = false;
    }
  }

  aiBtn?.addEventListener("click", () => run("ai", aiBtn, "Bezig met genereren…"));
  rulesBtn?.addEventListener("click", () => run("rules", rulesBtn, "Berekenen..."));

  /* losse adviezen wissen (prullenbak in de kaartkop / accordionkop) */
  document.querySelectorAll(".del-advice").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault(); // niet het accordion open/dichtklappen
      if (!confirm("Dit advies verwijderen?")) return;
      try {
        await api("/api/advice/" + btn.dataset.id, { method: "DELETE" });
        btn.closest(".card").remove();
        toast("Advies verwijderd");
        const kolom = document.querySelector(".advice-col");
        if (kolom && !kolom.querySelector(".card")) {
          const leeg = document.createElement("div");
          leeg.className = "card empty";
          leeg.innerHTML = "<p>Alle adviezen zijn verwijderd — genereer hierboven een nieuw advies.</p>";
          kolom.append(leeg);
        }
      } catch (err) { toast(err.message, false); }
    });
  });
}

/* ---------------- maaltijden ---------------- */
function initMeals() {
  const photo = $("#m-photo");
  const defaultDatum = $("#m-datum")?.value; // ingesteld in de template (= vandaag)

  /* ---- invoermethode: handmatig of AI-schatting ---- */
  const mealForm = $("#meal-form");
  function setMode(mode) {
    mealForm?.classList.toggle("mode-ai", mode === "ai");
    document.querySelectorAll("#meal-form .seg-btn").forEach((b) => {
      const actief = b.dataset.mode === mode;
      b.classList.toggle("active", actief);
      b.setAttribute("aria-pressed", String(actief));
    });
  }
  document.querySelectorAll("#meal-form .seg-btn").forEach((b) => {
    b.addEventListener("click", () => setMode(b.dataset.mode));
  });
  /* foto: zodra er een gekozen is, analyseert de AI meteen en verdwijnt het
     omschrijvingsveld — een aparte analyseknop is niet meer nodig */
  photo?.addEventListener("change", async () => {
    const file = photo.files[0];
    $("#m-photo-name").textContent = file ? file.name : "";
    $("#m-preview").innerHTML = file
      ? `<img src="${URL.createObjectURL(file)}" alt="preview van maaltijd">` : "";
    $("#ai-text-row")?.toggleAttribute("hidden", !!file);
    $("#ai-foto-titel")?.toggleAttribute("hidden", !!file);
    $("#btn-clear-photo").hidden = !file;
    if (file) await analyzePhoto();
  });

  async function analyzePhoto() {
    const file = photo?.files[0];
    if (!file) return;
    const statusEl = $("#m-photo-name");
    statusEl.textContent = "AI bekijkt de foto\u2026";
    try {
      const fd = new FormData();
      fd.append("photo", file);
      const r = await api("/api/meals/analyze", { method: "POST", body: fd });
      if (photo.files[0] === file) fillEstimate(r); // negeer verouderde analyse
    } catch (e) {
      toast(e.message, false);
    }
    statusEl.textContent = photo.files[0]?.name || "";
  }

  $("#btn-clear-photo")?.addEventListener("click", () => {
    photo.value = "";
    $("#m-photo-name").textContent = "";
    $("#m-preview").innerHTML = "";
    $("#ai-text-row")?.removeAttribute("hidden");
    $("#ai-foto-titel")?.removeAttribute("hidden");
    $("#btn-clear-photo").hidden = true;
  });

  /* ---- schatting op basis van een omschrijving ---- */
  const estimateBtn = $("#btn-estimate-text");
  estimateBtn?.addEventListener("click", async () => {
    const beschrijving = $("#m-beschrijving").value.trim();
    if (!beschrijving) { toast("Beschrijf eerst kort wat je gegeten hebt", false); return; }
    busy(estimateBtn, true, "AI schat de waarden\u2026");
    try {
      fillEstimate(await api("/api/meals/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ beschrijving }),
      }));
    } catch (e) {
      toast(e.message, false);
    }
    busy(estimateBtn, false);
  });

  /* schat-knop uitschakelen als er helemaal geen AI-backend is */
  fetch("/api/health").then((r) => r.json()).then((h) => {
    if (h.ai_api || h.ollama) return;
    if (estimateBtn) {
      estimateBtn.setAttribute("disabled", "");
      estimateBtn.title = "Start Ollama of stel een API in bij Instellingen";
    }
  }).catch(() => {});

  function fillEstimate(r) {
    if (r.naam) $("#m-naam").value = r.naam;
    $("#m-kcal").value = r.kcal ?? "";
    $("#m-eiwit").value = r.eiwit ?? "";
    $("#m-koolhydraten").value = r.koolhydraten ?? "";
    $("#m-vet").value = r.vet ?? "";
    if (r.opmerking) $("#m-opmerking").value = r.opmerking;
    setMode("manual"); // resultaat controleren gebeurt in de handmatige modus
    toast(`AI-schatting ingevuld (${r.bron}) \u2014 controleer de waarden`);
  }

  /* ---- bewerk-modus ---- */
  const EDIT_FIELDS = ["m-naam", "m-kcal", "m-eiwit", "m-koolhydraten", "m-vet", "m-opmerking", "m-beschrijving"];

  function resetEditMode() {
    $("#m-edit-id").value = "";
    setMode("manual");
    $("#meal-form-title").textContent = "Nieuwe maaltijd";
    $("#btn-save-manual").textContent = "Maaltijd toevoegen";
    $("#btn-edit-cancel").hidden = true;
    $("#photo-row").hidden = false;
    EDIT_FIELDS.forEach((id) => { const el = document.getElementById(id); if (el) el.value = ""; });
    if (defaultDatum) $("#m-datum").value = defaultDatum;
    photo.value = "";
    $("#m-photo-name").textContent = "";
    $("#m-preview").innerHTML = "";
    $("#ai-text-row")?.removeAttribute("hidden");
    $("#btn-clear-photo").hidden = true;
  }

  async function startEdit(id) {
    try {
      const m = await api("/api/meals/" + id);
      setMode("manual");
      $("#meal-form-title").textContent = "Maaltijd bewerken";
      $("#m-edit-id").value = m.id;
      $("#m-naam").value = m.naam || "";
      $("#m-kcal").value = m.kcal ?? "";
      $("#m-eiwit").value = m.eiwit ?? "";
      $("#m-koolhydraten").value = m.koolhydraten ?? "";
      $("#m-vet").value = m.vet ?? "";
      $("#m-opmerking").value = m.opmerking || "";
      $("#m-datum").value = m.datum || "";
      $("#btn-save-manual").textContent = "Wijzigingen opslaan";
      $("#btn-edit-cancel").hidden = false;
      $("#photo-row").hidden = true; // foto's van bestaande maaltijden blijven staan
      document.querySelector("#meal-form")?.scrollIntoView({ behavior: "smooth" });
    } catch (e) { toast(e.message, false); }
  }

  document.querySelectorAll(".edit-meal").forEach((btn) => {
    btn.addEventListener("click", () => startEdit(btn.dataset.id));
  });

  $("#btn-edit-cancel")?.addEventListener("click", resetEditMode);

  async function saveMeal(body) {
    await api("/api/meals/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast("Maaltijd opgeslagen");
    setTimeout(() => location.reload(), 700);
  }

  $("#btn-save-manual")?.addEventListener("click", async () => {
    const naam = $("#m-naam").value;
    if (!naam.trim()) { toast("Vul minimaal een naam in", false); return; }
    const body = {
      naam: naam, kcal: $("#m-kcal").value, eiwit: $("#m-eiwit").value,
      koolhydraten: $("#m-koolhydraten").value, vet: $("#m-vet").value,
      opmerking: $("#m-opmerking").value, datum: $("#m-datum").value,
    };
    const btn = $("#btn-save-manual");
    busy(btn, true, "Opslaan…");
    try {
      const editId = $("#m-edit-id").value;
      if (editId) {
        await api("/api/meals/" + editId, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        toast("Maaltijd bijgewerkt");
        setTimeout(() => location.reload(), 700);
      } else {
        await saveMeal(body); // foto's worden niet meer meegestuurd of bewaard
      }
    } catch (e) {
      toast(e.message, false);
      busy(btn, false);
    }
  });

  document.querySelectorAll(".del-meal").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Deze maaltijd verwijderen?")) return;
      try {
        await api("/api/meals/" + btn.dataset.id, { method: "DELETE" });
        const item = btn.closest(".list-item");
        const dag = item?.closest(".accordion");
        item.remove();
        const chip = $("#meals-count");
        if (chip) {
          chip.textContent = Math.max(0, (parseInt(chip.textContent, 10) || 0) - 1);
        }
        if (dag) {
          const over = dag.querySelectorAll(".list-item").length;
          if (!over) {
            dag.remove(); // lege dag verdwijnt uit de lijst
          } else {
            const meta = dag.querySelector(".acc-meta");
            if (meta) {
              let tot = 0;
              dag.querySelectorAll(".list-item").forEach((el) => {
                tot += parseFloat(el.dataset.kcal) || 0;
              });
              meta.textContent = `${over} ${over === 1 ? "maaltijd" : "maaltijden"} · ${Math.round(tot)} kcal`;
            }
          }
        }
        const kolom = $("#meals-day-list");
        if (kolom && !kolom.querySelector(".accordion") && !kolom.querySelector(".card.empty")) {
          const leeg = document.createElement("div");
          leeg.className = "card empty";
          leeg.innerHTML = "<p>Nog geen maaltijden gelogd.</p>";
          kolom.append(leeg);
        }
        toast("Maaltijd verwijderd");
      } catch (e) { toast(e.message, false); }
    });
  });
}

/* ---------------- trainingsschema ---------------- */
function initSchema() {
  const form = $("#schema-form");
  if (!form) return;
  const goal = $("#schema-goal");
  const rows = document.querySelectorAll(".schema-row");
  const planned = $("#schema-planned");
  const total = $("#schema-total");
  const goalVal = $("#schema-goal-val");
  const bar = $("#schema-bar");
  const hint = $("#schema-hint");

  function refresh() {
    let aantal = 0, minuten = 0;
    rows.forEach((row) => {
      const sport = row.querySelector("select").value;
      const min = parseInt(row.querySelector("input").value, 10) || 0;
      const vol = !!(sport && min > 0);
      row.classList.toggle("filled", vol);
      if (vol) { aantal += 1; minuten += min; }
    });
    const doel = parseInt(goal?.value, 10) || 0;
    if (planned) planned.textContent = aantal;
    if (total) total.textContent = minuten;
    if (goalVal) goalVal.textContent = doel || "\u2013";
    if (bar) bar.style.width = doel ? Math.min(100, Math.round(aantal / doel * 100)) + "%" : "0%";
    if (hint) {
      hint.textContent = doel && aantal >= doel
        ? `Je staat op ${aantal} trainingen \u2014 weekdoel van ${doel} gehaald (of meer).`
        : `Nu ${aantal} training(en) gepland${doel ? `, doel is ${doel}` : ""}. Kies per dag een sport en vul de minuten in.`;
    }
  }

  rows.forEach((row) => {
    row.querySelector("select").addEventListener("change", refresh);
    row.querySelector("input").addEventListener("input", refresh);
  });
  goal?.addEventListener("input", refresh);
  refresh();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const entries = [];
    rows.forEach((row) => {
      const sport = row.querySelector("select").value;
      const min = parseInt(row.querySelector("input").value, 10) || 0;
      if (sport && min > 0) {
        entries.push({ weekday: row.dataset.weekday, sport, minutes: min });
      }
    });
    const btn = $("#btn-save-schema");
    busy(btn, true, "Opslaan…");
    try {
      const r = await api("/api/schema/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          week: form.dataset.week,
          sessions_goal: goal?.value || null,
          entries,
        }),
      });
      toast(`Schema opgeslagen: ${r.opgeslagen} training(en) in week ${form.dataset.week.split("-W")[1]}`);
    } catch (err) {
      toast(err.message, false);
    }
    busy(btn, false);
  });

  /* ---- AI-advies bij dit schema ---- */
  const adviceBtn = $("#btn-schema-advice");
  adviceBtn?.addEventListener("click", async () => {
    busy(adviceBtn, true, "Bezig met genereren…");
    try {
      await api("/api/schema/advice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ week: form.dataset.week }),
      });
      toast("AI-trainingsadvies klaar");
      setTimeout(() => location.reload(), 900);
    } catch (err) {
      toast(err.message, false);
      busy(adviceBtn, false);
    }
  });
}

/* ---------------- instellingen ---------------- */
function initSettings() {
  const providerSelect = document.querySelector("[name='ai_provider']");
  function updateProviderFields() {
    if (!providerSelect) return;
    const cloud = providerSelect.value !== "ollama";
    ["f-api-key", "f-api-base", "f-api-model"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = !cloud;
    });
    const ollamaVeld = document.getElementById("f-ollama-model");
    const ollamaHint = document.getElementById("ollama-hint");
    if (ollamaVeld) ollamaVeld.hidden = cloud;
    if (ollamaHint) ollamaHint.hidden = cloud;
  }
  providerSelect?.addEventListener("change", updateProviderFields);
  updateProviderFields();

  async function save(fields, statusEl, okMsg) {
    const data = {};
    fields.forEach((name) => {
      const el = document.querySelector(`[name="${name}"]`);
      if (el) data[name] = el.value;
    });
    try {
      await api("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (statusEl) statusEl.textContent = "✓ opgeslagen";
      if (okMsg) toast(okMsg);
    } catch (e) { toast(e.message, false); }
  }

  $("#btn-save-profile")?.addEventListener("click", () =>
    save(["age", "sex", "height_cm", "weight_kg", "step_goal", "goal"], $("#profile-status"), "Profiel opgeslagen"));
  $("#btn-save-ai")?.addEventListener("click", () =>
    save(["model_advice", "ai_provider", "ai_api_key", "ai_base_url", "ai_model"],
         $("#ai-status"), "AI-voorkeur opgeslagen"));
  $("#btn-ai-test")?.addEventListener("click", async () => {
    const statusEl = $("#ai-status");
    if (statusEl) statusEl.textContent = "Verbinden…";
    try {
      await save(["model_advice", "ai_provider", "ai_api_key", "ai_base_url", "ai_model"], null, "");
      const r = await api("/api/ai/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (statusEl) statusEl.textContent = `✓ ${r.bron} — antwoord: ${r.antwoord}`;
    } catch (e) { if (statusEl) statusEl.textContent = e.message; }
  });
  $("#btn-save-garmin")?.addEventListener("click", () =>
    save(["garmin_email", "garmin_password", "sync_days"], $("#garmin-status"), "Garmin-toegang opgeslagen"));

  /* ---- 2FA-loginflow ---- */
  const loginState = $("#garmin-login-state");
  let pollTimer = null;

  function setLoginUI(status, message) {
    if (loginState) loginState.textContent = message || status;
    const mfaRow = $("#mfa-row");
    if (mfaRow) mfaRow.hidden = status !== "mfa_required";
  }

  function pollLogin() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const s = await api("/api/garmin/login/status");
        setLoginUI(s.status, s.message);
        if (s.status === "ok") {
          clearInterval(pollTimer); pollTimer = null;
          toast(s.message);
          setTimeout(() => location.reload(), 1200);
        } else if (s.status === "error") {
          clearInterval(pollTimer); pollTimer = null;
          toast(s.message, false);
        }
      } catch (e) { /* server tijdelijk onbereikbaar: gewoon doorgaan */ }
    }, 2000);
  }

  $("#btn-garmin-login")?.addEventListener("click", async () => {
    const btn = $("#btn-garmin-login");
    busy(btn, true, "Verbinden…");
    try {
      await save(["garmin_email", "garmin_password", "sync_days"], null, "");
      await api("/api/garmin/login/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      setLoginUI("in_progress", "Verbinding maken met Garmin…");
      pollLogin();
    } catch (e) {
      toast(e.message, false);
    }
    busy(btn, false);
  });

  $("#btn-mfa")?.addEventListener("click", async () => {
    const code = $("#mfa-code").value.trim();
    if (!code) { toast("Vul de code uit je Garmin-app, sms of e-mail in", false); return; }
    try {
      await api("/api/garmin/login/mfa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      $("#mfa-code").value = "";
      setLoginUI("in_progress", "Code gecontroleerd bij Garmin…");
    } catch (e) { toast(e.message, false); }
  });

  $("#mfa-code")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#btn-mfa")?.click();
  });

  $("#btn-garmin-logout")?.addEventListener("click", async () => {
    if (!confirm("Garmin-tokens wissen? De volgende login vraagt weer om 2FA.")) return;
    try {
      await api("/api/garmin/logout", { method: "POST" });
      toast("Garmin-tokens gewist");
    } catch (e) { toast(e.message, false); }
  });

  api("/api/garmin/login/status").then((s) => {
    if (s.status === "in_progress" || s.status === "mfa_required") {
      setLoginUI(s.status, s.message);
      pollLogin();
    }
  }).catch(() => {});

  $("#btn-sync2")?.addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    busy(btn, true, "Syncen…");
    try {
      const r = await api("/api/garmin/sync", { method: "POST" });
      toast(`Sync voltooid: ${r.dagen} dag(en)`);
    } catch (e) { toast(e.message, false); }
    busy(btn, false);
  });

  const csvInput = $("#csv-files");
  csvInput?.addEventListener("change", () => {
    const names = [...(csvInput.files || [])].map((f) => f.name).join(", ");
    $("#csv-name").textContent = names;
  });

  $("#btn-csv")?.addEventListener("click", async () => {
    const files = csvInput?.files;
    if (!files || !files.length) { toast("Kies eerst een of meer CSV-bestanden", false); return; }
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    try {
      const r = await api("/api/garmin/csv", { method: "POST", body: fd });
      toast(`${r.rijen} rijen geïmporteerd`);
      setTimeout(() => location.reload(), 900);
    } catch (e) { toast(e.message, false); }
  });

  $("#btn-reset")?.addEventListener("click", async () => {
    if (!confirm("Alles wissen (metingen, maaltijden, advies en instellingen)?")) return;
    try {
      await api("/api/reset", { method: "POST" });
      toast("Alle data gewist");
      setTimeout(() => location.reload(), 700);
    } catch (e) { toast(e.message, false); }
  });

  /* ---- gebruikersaccounts ---- */
  const usersBox = $("#users-lijst");
  const MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
                   "augustus", "september", "oktober", "november", "december"];

  function datumNL(iso) {
    const d = new Date((iso || "").replace(" ", "T"));
    if (isNaN(d)) return iso || "";
    return `${d.getDate()} ${MAANDEN[d.getMonth()]} ${d.getFullYear()}`;
  }

  async function laadGebruikers() {
    if (!usersBox) return;
    try {
      const lijst = await api("/api/gebruikers");
      usersBox.innerHTML = "";
      if (!lijst.length) {
        const p = document.createElement("p");
        p.className = "hint card-intro";
        p.textContent = "Nog geen extra accounts — vul hieronder een naam en wachtwoord in.";
        usersBox.append(p);
        return;
      }
      lijst.forEach((g) => {
        const rij = document.createElement("div");
        rij.className = "list-item";
        const tekst = document.createElement("div");
        tekst.className = "list-text";
        const nm = document.createElement("div");
        nm.className = "list-head";
        nm.textContent = g.username;
        const sub = document.createElement("div");
        sub.className = "list-sub";
        sub.textContent = g.created_at ? `account sinds ${datumNL(g.created_at)}` : "account";
        tekst.append(nm, sub);
        const knop = document.createElement("button");
        knop.type = "button";
        knop.className = "icon-btn del-user";
        knop.dataset.id = g.id;
        knop.setAttribute("aria-label", "Account verwijderen");
        knop.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6M14 11v6"/></svg>';
        knop.addEventListener("click", async () => {
          if (!confirm(`Account '${g.username}' verwijderen?`)) return;
          try {
            await api("/api/gebruikers/" + g.id, { method: "DELETE" });
            toast("Account verwijderd");
            laadGebruikers();
          } catch (e) { toast(e.message, false); }
        });
        rij.append(tekst, knop);
        usersBox.append(rij);
      });
    } catch (e) {
      usersBox.innerHTML = "";
      const p = document.createElement("p");
      p.className = "hint card-intro";
      p.textContent = e.message;
      usersBox.append(p);
    }
  }

  $("#btn-user-add")?.addEventListener("click", async () => {
    const naam = $("#u-naam").value.trim();
    const wacht = $("#u-wacht").value;
    const status = $("#users-status");
    if (naam.length < 3) { toast("Gebruikersnaam: minimaal 3 tekens", false); return; }
    if (wacht.length < 4) { toast("Wachtwoord: minimaal 4 tekens", false); return; }
    try {
      await api("/api/gebruikers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gebruiker: naam, wachtwoord: wacht }),
      });
      toast("Account opgeslagen");
      $("#u-naam").value = "";
      $("#u-wacht").value = "";
      if (status) status.textContent = "";
      laadGebruikers();
    } catch (e) { if (status) status.textContent = e.message; }
  });

  laadGebruikers();
}

/* ---------------- activiteiten ---------------- */
function initActivities() {
  const syncBtn = $("#btn-sync-act");
  syncBtn?.addEventListener("click", async () => {
    busy(syncBtn, true, "Syncen…");
    try {
      const r = await api("/api/garmin/sync", { method: "POST" });
      toast(`Sync voltooid: ${r.dagen} dag(en) + ${r.activiteiten} activiteit(en)`);
      setTimeout(() => location.reload(), 900);
    } catch (e) {
      toast(e.message, false);
      busy(syncBtn, false);
    }
  });

  /* ---- detailvenster per activiteit ---- */
  const modal = $("#act-modal");
  if (modal && modal.showModal) {
    const title = $("#act-modal-title");
    const body = $("#act-modal-body");

    document.querySelectorAll(".act-row").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tpl = btn.querySelector("template.act-detail");
        if (!tpl) return;
        title.textContent = btn.dataset.name || "Activiteit";
        body.innerHTML = "";
        body.append(tpl.content.cloneNode(true));
        modal.showModal();
      });
    });

    /* alle sluit-wegen via dezelfde uit-animatie */
    function closeModal() {
      if (!modal.open || modal.classList.contains("closing")) return;
      modal.classList.add("closing");
      setTimeout(() => {
        modal.close();
        modal.classList.remove("closing");
        body.innerHTML = "";
      }, 170);
    }

    $("#act-modal-close")?.addEventListener("click", closeModal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal(); // klik op de donkere achtergrond
    });
    modal.addEventListener("cancel", (e) => {
      e.preventDefault(); // Esc zelf animeren in plaats van instant sluiten
      closeModal();
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  drawSparks();
  initReveal();
  loadStatus();
  initDashboard();
  initAdvice();
  initMeals();
  initActivities();
  initSchema();
  initSettings();
});