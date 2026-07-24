/**
 * MOVA Litter Box card for Home Assistant.
 *
 * A compact dashboard control (vacuum-card style) for the MOVA MeowgicPod
 * litter box: shows the current status and one-tap Clean / Level / Empty
 * actions, plus Pause / Resume / Stop and the last cat visit.
 *
 * Example dashboard config:
 *
 *   type: custom:mova-litter-box-card
 *   name: Casota dos Gatos            # optional, defaults to the status name
 *   status: sensor.casota_dos_gatos_status
 *   clean: button.casota_dos_gatos_start_cleaning
 *   level: button.casota_dos_gatos_level_litter
 *   empty: button.casota_dos_gatos_empty_waste
 *   pause: button.casota_dos_gatos_pause       # optional
 *   resume: button.casota_dos_gatos_resume     # optional
 *   stop: button.casota_dos_gatos_stop         # optional
 *   last_cat: sensor.casota_dos_gatos_last_cat # optional
 *   last_weight: sensor.casota_dos_gatos_last_cat_weight  # optional
 *
 * by CookieBytes 🍪
 */

const STATUS = {
  standby: { label: "Standby", color: "var(--disabled-text-color, #9e9e9e)", icon: "mdi:paw" },
  cleaning: { label: "Cleaning", color: "#3391ff", icon: "mdi:broom" },
  cleaning_paused: { label: "Cleaning paused", color: "#f0a020", icon: "mdi:pause" },
  emptying: { label: "Emptying", color: "#3391ff", icon: "mdi:delete-empty" },
  emptying_paused: { label: "Emptying paused", color: "#f0a020", icon: "mdi:pause" },
  leveling: { label: "Leveling", color: "#3391ff", icon: "mdi:dots-horizontal" },
  leveling_paused: { label: "Leveling paused", color: "#f0a020", icon: "mdi:pause" },
  canceling_cleaning: { label: "Canceling…", color: "#f0a020", icon: "mdi:close" },
  canceling_emptying: { label: "Canceling…", color: "#f0a020", icon: "mdi:close" },
  canceling_leveling: { label: "Canceling…", color: "#f0a020", icon: "mdi:close" },
  weighing_protection: { label: "Weighing protection", color: "#f0a020", icon: "mdi:scale" },
  air_purification: { label: "Air purification", color: "#26a69a", icon: "mdi:air-filter" },
  safety_escape: { label: "Safety escape", color: "#e53935", icon: "mdi:alert" },
  device_abnormal: { label: "Device abnormal", color: "#e53935", icon: "mdi:alert-circle" },
};

class MovaLitterBoxCard extends HTMLElement {
  setConfig(config) {
    if (!config.status && !config.clean) {
      throw new Error("Set at least `status` and the action entities (clean/level/empty).");
    }
    this._config = config;
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._update();
  }

  _st(entity) {
    return entity && this._hass && this._hass.states[entity];
  }

  _press(entity) {
    if (!entity) return;
    this._hass.callService("button", "press", { entity_id: entity });
  }

  _statusInfo() {
    const s = this._st(this._config.status);
    const raw = s ? s.state : "unknown";
    return STATUS[raw] || { label: raw, color: "var(--primary-text-color)", icon: "mdi:paw" };
  }

  _timeAgo(iso) {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (isNaN(then)) return "";
    const secs = Math.max(0, (Date.now() - then) / 1000);
    if (secs < 90) return "just now";
    const mins = Math.round(secs / 60);
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} h ago`;
    return `${Math.round(hrs / 24)} d ago`;
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        .head { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
        .badge { width:44px; height:44px; border-radius:12px; display:flex;
                 align-items:center; justify-content:center; flex:0 0 auto; }
        .badge ha-icon { --mdc-icon-size:26px; color:#fff; }
        .titles { display:flex; flex-direction:column; min-width:0; }
        .name { font-size:1.05rem; font-weight:600; color:var(--primary-text-color);
                white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .state { font-size:.9rem; }
        .primary { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
        .secondary { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:8px; }
        button.act { display:flex; flex-direction:column; align-items:center; gap:6px;
                     padding:12px 4px; border:none; border-radius:12px; cursor:pointer;
                     background:var(--secondary-background-color); color:var(--primary-text-color);
                     font-size:.82rem; transition:filter .15s, opacity .15s; }
        button.act:hover { filter:brightness(1.06); }
        button.act[disabled] { opacity:.4; cursor:not-allowed; }
        button.act ha-icon { --mdc-icon-size:24px; }
        button.prim { background:var(--primary-color); color:var(--text-primary-color,#fff); }
        .foot { margin-top:14px; font-size:.85rem; color:var(--secondary-text-color);
                display:flex; align-items:center; gap:6px; }
        .foot ha-icon { --mdc-icon-size:18px; }
        .hidden { display:none; }
      </style>
      <ha-card>
        <div class="head">
          <div class="badge" id="badge"><ha-icon id="badgeIcon"></ha-icon></div>
          <div class="titles">
            <div class="name" id="name"></div>
            <div class="state" id="state"></div>
          </div>
        </div>
        <div class="primary">
          <button class="act prim" id="clean"><ha-icon icon="mdi:broom"></ha-icon><span>Clean</span></button>
          <button class="act prim" id="level"><ha-icon icon="mdi:dots-horizontal"></ha-icon><span>Level</span></button>
          <button class="act prim" id="empty"><ha-icon icon="mdi:delete-empty"></ha-icon><span>Empty</span></button>
        </div>
        <div class="secondary" id="secondary">
          <button class="act" id="pause"><ha-icon icon="mdi:pause"></ha-icon><span>Pause</span></button>
          <button class="act" id="resume"><ha-icon icon="mdi:play"></ha-icon><span>Resume</span></button>
          <button class="act" id="stop"><ha-icon icon="mdi:stop"></ha-icon><span>Stop</span></button>
        </div>
        <div class="foot hidden" id="foot"><ha-icon icon="mdi:cat"></ha-icon><span id="footText"></span></div>
      </ha-card>
    `;
    const bind = (id, entity) => {
      const el = root.getElementById(id);
      if (!el) return;
      if (!entity) { el.classList.add("hidden"); return; }
      el.addEventListener("click", () => this._press(entity));
    };
    bind("clean", this._config.clean);
    bind("level", this._config.level);
    bind("empty", this._config.empty);
    bind("pause", this._config.pause);
    bind("resume", this._config.resume);
    bind("stop", this._config.stop);
    // Hide the secondary row entirely if none configured
    if (!this._config.pause && !this._config.resume && !this._config.stop) {
      root.getElementById("secondary").classList.add("hidden");
    }
    this._root = root;
    this._built = true;
  }

  _update() {
    const root = this._root;
    if (!root) return;
    const info = this._statusInfo();
    const statusState = this._st(this._config.status);
    const name = this._config.name
      || (statusState && statusState.attributes.friendly_name
        ? statusState.attributes.friendly_name.replace(/\s*Status$/i, "")
        : "MOVA Litter Box");
    root.getElementById("name").textContent = name;
    const stateEl = root.getElementById("state");
    stateEl.textContent = info.label;
    stateEl.style.color = info.color;
    root.getElementById("badge").style.background = info.color;
    root.getElementById("badgeIcon").setAttribute("icon", info.icon);

    // Footer: last cat + weight + time
    const cat = this._st(this._config.last_cat);
    const weight = this._st(this._config.last_weight);
    const foot = root.getElementById("foot");
    if (cat || weight) {
      const bits = [];
      if (cat && cat.state && cat.state !== "unknown" && cat.state !== "unavailable") bits.push(cat.state);
      if (weight && weight.state && !isNaN(parseFloat(weight.state))) bits.push(`${weight.state} kg`);
      const when = weight ? this._timeAgo(weight.last_changed) : "";
      if (when) bits.push(when);
      if (bits.length) {
        root.getElementById("footText").textContent = "Last: " + bits.join(" · ");
        foot.classList.remove("hidden");
      } else {
        foot.classList.add("hidden");
      }
    }
  }

  getCardSize() {
    return this._config && (this._config.pause || this._config.stop) ? 4 : 3;
  }

  static getStubConfig() {
    return {
      status: "sensor.mova_litter_box_status",
      clean: "button.mova_litter_box_start_cleaning",
      level: "button.mova_litter_box_level_litter",
      empty: "button.mova_litter_box_empty_waste",
    };
  }
}

customElements.define("mova-litter-box-card", MovaLitterBoxCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "mova-litter-box-card",
  name: "MOVA Litter Box",
  description: "Clean / Level / Empty control card for the MOVA litter box.",
  preview: false,
});
console.info("%c MOVA-LITTER-BOX-CARD %c loaded ", "background:#dc9248;color:#fff;border-radius:3px 0 0 3px", "background:#6b3008;color:#fff;border-radius:0 3px 3px 0");
