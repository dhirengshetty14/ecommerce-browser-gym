// Ghost cursor — visualizes where the agent is clicking, filling, selecting.
//
// Injected into EVERY page via Playwright's context.add_init_script(). The
// harness moves this cursor to the target element BEFORE executing the
// underlying Playwright action. Effect: when you watch a headed run, you
// see a red glowing dot float across the screen, an action label appears
// above it ("CLICK", "FILL: Studio Laptop"), and the target element
// pulses briefly when the action fires.
//
// All of this is decoration — it does NOT affect the verifier or the
// agent's observation. It only exists so humans can SEE the agent.

(function () {
  if (window.__shopgym_cursor) return;  // idempotent

  // ─── Build the cursor element ───────────────────────────────
  const cursor = document.createElement('div');
  cursor.id = '__shopgym_cursor';
  cursor.style.cssText = [
    'position: fixed',
    'top: 50%',
    'left: 50%',
    'width: 28px',
    'height: 28px',
    'pointer-events: none',
    'z-index: 999999',
    'transform: translate(-50%, -50%)',
    'transition: top 0.45s cubic-bezier(.4,0,.2,1), left 0.45s cubic-bezier(.4,0,.2,1)',
    'background: radial-gradient(circle, rgba(239,68,68,0.95) 0%, rgba(239,68,68,0.55) 45%, rgba(239,68,68,0) 75%)',
    'border: 2px solid rgba(255,255,255,1)',
    'border-radius: 50%',
    'box-shadow: 0 0 22px rgba(239,68,68,0.85), 0 0 8px rgba(239,68,68,0.55), 0 2px 6px rgba(0,0,0,0.3)',
    'opacity: 0.95',
  ].join(';');

  // ─── Action label (tooltip-style) ────────────────────────────
  const label = document.createElement('div');
  label.id = '__shopgym_action_label';
  label.style.cssText = [
    'position: fixed',
    'top: 50%',
    'left: 50%',
    'transform: translate(-50%, -200%)',
    'background: rgba(15, 23, 42, 0.94)',
    'color: white',
    'padding: 6px 12px',
    'border-radius: 6px',
    'font-size: 12px',
    'font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    'font-weight: 700',
    'letter-spacing: 0.5px',
    'pointer-events: none',
    'z-index: 1000000',
    'transition: top 0.45s cubic-bezier(.4,0,.2,1), left 0.45s cubic-bezier(.4,0,.2,1), opacity 0.3s',
    'opacity: 0',
    'box-shadow: 0 4px 12px rgba(0,0,0,0.3)',
    'white-space: nowrap',
    'max-width: 320px',
    'overflow: hidden',
    'text-overflow: ellipsis',
  ].join(';');

  // ─── Pulse ring (radiates from target on action fire) ────────
  const ring = document.createElement('div');
  ring.id = '__shopgym_pulse_ring';
  ring.style.cssText = [
    'position: fixed',
    'top: 50%',
    'left: 50%',
    'width: 20px',
    'height: 20px',
    'border: 3px solid rgba(239,68,68,0.9)',
    'border-radius: 50%',
    'pointer-events: none',
    'z-index: 999998',
    'transform: translate(-50%, -50%) scale(1)',
    'opacity: 0',
    'transition: transform 0.6s ease-out, opacity 0.6s ease-out',
  ].join(';');

  // Style block for global highlight + step counter
  const style = document.createElement('style');
  style.textContent = `
    [data-shopgym-target] {
      outline: 3px solid rgba(239, 68, 68, 0.85) !important;
      outline-offset: 2px !important;
      box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.15) !important;
      transition: outline-color 0.3s, box-shadow 0.3s !important;
    }
    #__shopgym_step_badge {
      position: fixed;
      bottom: 16px; right: 16px;
      background: rgba(15, 23, 42, 0.92);
      color: white;
      padding: 8px 14px;
      border-radius: 9999px;
      font-size: 13px;
      font-family: -apple-system, sans-serif;
      font-weight: 700;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      pointer-events: none;
      z-index: 999997;
      display: flex; align-items: center; gap: 6px;
    }
    #__shopgym_step_badge .dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: rgb(34, 197, 94);
      box-shadow: 0 0 8px rgba(34,197,94,0.9);
      animation: shopgym_pulse 1.5s ease-in-out infinite;
    }
    @keyframes shopgym_pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%      { opacity: 0.5; transform: scale(0.7); }
    }
  `;

  // ─── Step counter badge (bottom-right) ───────────────────────
  const badge = document.createElement('div');
  badge.id = '__shopgym_step_badge';
  badge.innerHTML = '<span class="dot"></span><span id="__shopgym_step_text">agent ready</span>';

  // ─── Wait for DOM ready, then attach ────────────────────────
  function attach() {
    document.head.appendChild(style);
    document.body.appendChild(cursor);
    document.body.appendChild(label);
    document.body.appendChild(ring);
    document.body.appendChild(badge);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }

  // ─── Public API ──────────────────────────────────────────────
  window.__shopgym_cursor = {
    /**
     * Move the ghost cursor to the centre of the matching element.
     * Returns {x, y} on success or null if selector didn't match.
     */
    moveTo: function (selector) {
      const el = document.querySelector(selector);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      cursor.style.left = cx + 'px';
      cursor.style.top = cy + 'px';
      label.style.left = cx + 'px';
      label.style.top = (cy - 30) + 'px';
      ring.style.left = cx + 'px';
      ring.style.top = cy + 'px';
      // Briefly mark the element as a target so the CSS rule kicks in
      el.setAttribute('data-shopgym-target', 'true');
      setTimeout(() => el.removeAttribute('data-shopgym-target'), 800);
      return { x: cx, y: cy };
    },

    /**
     * Show the action label near the cursor for ~1.6s.
     */
    showAction: function (kind, detail) {
      const text = detail
        ? kind.toUpperCase() + ': ' + String(detail).slice(0, 50)
        : kind.toUpperCase();
      label.textContent = text;
      label.style.opacity = '1';
      // Color by action kind
      const colors = {
        CLICK: 'rgba(239, 68, 68, 0.94)',
        FILL: 'rgba(59, 130, 246, 0.94)',
        SELECT: 'rgba(168, 85, 247, 0.94)',
        SUBMIT: 'rgba(34, 197, 94, 0.94)',
        CHECK: 'rgba(245, 158, 11, 0.94)',
        NAVIGATE: 'rgba(15, 118, 110, 0.94)',
      };
      label.style.background = colors[kind.toUpperCase()] || 'rgba(15, 23, 42, 0.94)';
      setTimeout(() => { label.style.opacity = '0'; }, 1600);
    },

    /**
     * Fire the pulse ring at current cursor location.
     */
    pulse: function () {
      ring.style.transform = 'translate(-50%, -50%) scale(1)';
      ring.style.opacity = '0.95';
      // Force reflow then animate out
      void ring.offsetWidth;
      ring.style.transform = 'translate(-50%, -50%) scale(3.5)';
      ring.style.opacity = '0';
    },

    /**
     * Update the step counter badge in bottom-right.
     */
    setStep: function (step, kind) {
      const txt = document.getElementById('__shopgym_step_text');
      if (txt) txt.textContent = `step ${step} — ${kind}`;
    },
  };
})();
