(function applySavedTheme() {
  try {
    const theme = globalThis.localStorage.getItem("mbe-theme");
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  } catch (_) {
    // Storage can be unavailable in privacy modes; system theme remains valid.
  }
})();
