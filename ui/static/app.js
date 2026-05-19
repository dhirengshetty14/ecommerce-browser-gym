// ShopGym client-side enhancements via Alpine.js.
// The pages are server-rendered (Jinja). This file just adds the
// interactive bits that make the site feel like real e-commerce:
//   - Toast notifications (transient)
//   - Search autocomplete (client-side index)
//   - Cart drawer preview
//   - Modal dialog management
//
// All elements remain accessible via data-test-id selectors for the
// browser agent — Alpine.js just adds dynamic show/hide behavior.

window.shopGym = function () {
  return {
    // ─── TOAST QUEUE ──────────────────────────────────────────────
    toasts: [],
    nextToastId: 1,

    toast(body, kind = "info", ttlMs = 3500) {
      const id = this.nextToastId++;
      this.toasts.push({ id, body, kind });
      setTimeout(() => {
        this.toasts = this.toasts.filter((t) => t.id !== id);
      }, ttlMs);
    },

    // ─── AUTOCOMPLETE ─────────────────────────────────────────────
    // Static product/category suggestion index. In a real app this
    // would be an AJAX call. Kept synchronous so the agent's
    // observation is deterministic.
    _searchIndex: [
      "Wireless Mouse", "Wireless Gaming Mouse", "Mechanical Keyboard",
      "Wireless Keyboard", "Studio Laptop 14", "Pro Laptop X1",
      "Budget Laptop Lite", "24-inch Monitor", "27-inch Monitor",
      "Bluetooth Headphone Premium", "Bluetooth Headphone Studio",
      "Bluetooth Headphone Lite", "Bluetooth Speaker",
      "Cotton T-Shirt", "Pullover Hoodie", "Modern Desk Lamp",
      "Ceramic Coffee Mug Set", "Premium Dog Food",
      "Project Hail Mary", "Sapiens", "The Joy of Cooking",
      "Office Display Pro",
    ],

    autocompleteSuggestions(query) {
      if (!query || query.length < 1) return [];
      const q = query.toLowerCase();
      return this._searchIndex
        .filter((name) => name.toLowerCase().includes(q))
        .slice(0, 6);
    },

    // ─── INIT ─────────────────────────────────────────────────────
    initGym() {
      // Surface any flash messages as toasts too — they auto-dismiss.
      // Real e-commerce sites do this for the "Added to cart!" pattern.
      document.querySelectorAll("[data-test-id^='flash-']").forEach((el) => {
        const kind = el.getAttribute("data-test-id").replace("flash-", "");
        const body = el.textContent.trim();
        if (body) {
          // Skip if already shown server-side (just keep the banner).
        }
      });

      // Click handler: dismiss modals on Escape
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          document.querySelectorAll("[data-modal-open='true']")
            .forEach((m) => m.setAttribute("data-modal-open", "false"));
        }
      });
    },
  };
};

// Quick-add-to-cart helper for product cards (optional micro-interaction).
// The actual add still goes through the form POST — this just shows a
// toast for visual feedback.
window.flashToast = function (body, kind) {
  const evt = new CustomEvent("shopgym:toast", { detail: { body, kind } });
  window.dispatchEvent(evt);
};
