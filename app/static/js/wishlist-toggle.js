(function () {
  var buttons = Array.from(document.querySelectorAll("[data-wishlist-toggle]"));
  if (!buttons.length) return;

  function updateButtons(tmdbId, active) {
    buttons.forEach(function (button) {
      if (button.dataset.tmdbId !== tmdbId) return;
      var movieTitle = button.dataset.movieTitle;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("aria-label", (active ? "찜 해제: " : "찜하기: ") + movieTitle);
      button.title = active ? "찜 해제" : "찜하기";
    });
  }

  buttons.forEach(function (button) {
    button.addEventListener("click", async function () {
      if (button.dataset.authenticated !== "true") {
        var loginTrigger = document.getElementById("login-teaser-trigger");
        if (loginTrigger) loginTrigger.click();
        return;
      }

      var nextState = button.getAttribute("aria-pressed") !== "true";
      buttons.forEach(function (item) {
        if (item.dataset.tmdbId === button.dataset.tmdbId) item.disabled = true;
      });

      try {
        var response = await fetch(button.dataset.wishlistUrl, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({is_wishlisted: nextState})
        });
        if (response.redirected) {
          window.location.href = response.url;
          return;
        }
        if (!response.ok) throw new Error("wishlist request failed");
        var result = await response.json();
        updateButtons(button.dataset.tmdbId, Boolean(result.is_wishlisted));
      } catch (error) {
        console.error("Wishlist update failed", error);
        window.alert("찜 상태를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.");
      } finally {
        buttons.forEach(function (item) {
          if (item.dataset.tmdbId === button.dataset.tmdbId) item.disabled = false;
        });
      }
    });
  });
})();
