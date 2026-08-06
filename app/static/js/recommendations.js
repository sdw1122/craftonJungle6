(() => {
  const section = document.querySelector("#recommendation-section");
  if (!section) return;

  const grid = section.querySelector("#recommendation-grid");
  const loading = section.querySelector("#recommendation-loading");
  const error = section.querySelector("#recommendation-error");
  const empty = section.querySelector("#recommendation-empty");
  const meta = section.querySelector("#recommendation-meta");
  const refresh = section.querySelector("#recommendation-refresh");
  const postUrl = section.dataset.postUrl;

  function setState(state) {
    loading.hidden = state !== "loading";
    error.hidden = state !== "error";
    empty.hidden = state !== "empty";
    grid.hidden = state !== "ready";
    meta.hidden = state !== "ready";
    refresh.disabled = state === "loading";
  }

  async function request(url, options = {}) {
    const { headers = {}, ...requestOptions } = options;
    const response = await fetch(url, {
      credentials: "same-origin",
      ...requestOptions,
      headers: { Accept: "application/json", ...headers },
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
      throw new Error(payload?.message || "추천 요청에 실패했습니다.");
    }
    return payload;
  }

  function textElement(tagName, className, value) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    element.textContent = value;
    return element;
  }

  function movieCard(movie) {
    const article = document.createElement("article");
    article.className = "recommendation-card";

    const link = document.createElement("a");
    link.href = `/movies/${encodeURIComponent(movie.tmdb_id)}`;
    link.className = "recommendation-poster-link";

    if (movie.poster_url) {
      const image = document.createElement("img");
      image.src = movie.poster_url;
      image.alt = `${movie.title || movie.original_title} 포스터`;
      image.loading = "lazy";
      image.className = "recommendation-poster";
      link.appendChild(image);
    } else {
      link.appendChild(textElement("div", "poster-placeholder recommendation-poster", "포스터 없음"));
    }

    const body = document.createElement("div");
    body.className = "recommendation-card-body";
    const badges = document.createElement("div");
    badges.className = "recommendation-badges";
    (movie.provider_matches || []).forEach((provider) => {
      badges.appendChild(textElement("span", "provider-badge", provider));
    });
    const score = Math.max(0, Math.min(100, Math.round(Number(movie.score || 0) * 100)));
    badges.appendChild(textElement("span", "score-badge", `${score}% 취향 일치`));

    const titleLink = document.createElement("a");
    titleLink.href = link.href;
    titleLink.className = "recommendation-title-link";
    titleLink.appendChild(textElement("h2", "", movie.title || movie.original_title || "제목 없음"));

    const facts = [
      movie.release_date ? movie.release_date.slice(0, 4) : "개봉일 미정",
      ...(movie.genres || []).slice(0, 2),
    ].join(" · ");

    body.append(
      badges,
      titleLink,
      textElement("p", "recommendation-facts", facts),
      textElement("p", "recommendation-reason", movie.reason || "취향과 잘 맞는 영화예요."),
    );
    article.append(link, body);
    return article;
  }

  function render(payload) {
    const movies = payload?.recommendations || [];
    if (!movies.length) {
      setState("empty");
      return;
    }
    grid.replaceChildren(...movies.map(movieCard));
    const generated = payload.generated_at ? new Date(payload.generated_at) : null;
    const sourceLabels = {
      ai: "AI 맞춤 추천",
      rules: "취향 기반 추천",
      cache: "저장된 맞춤 추천",
      stale: "최근 맞춤 추천",
    };
    meta.textContent = `${sourceLabels[payload.source] || "맞춤 추천"}${
      generated && !Number.isNaN(generated.valueOf())
        ? ` · ${generated.toLocaleString("ko-KR")} 생성`
        : ""
    }`;
    setState("ready");
  }

  async function generate(force) {
    setState("loading");
    try {
      const payload = await request(postUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force, limit: 10 }),
      });
      render(payload);
    } catch (requestError) {
      error.querySelector("span").textContent = requestError.message;
      setState("error");
    }
  }

  refresh.addEventListener("click", () => generate(true));
  setState("empty");
})();
