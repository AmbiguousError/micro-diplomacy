/*
 * Fetches a markdown file served by this same app (e.g. /RULES.md) and
 * renders it into a container element using marked.js (must already be
 * loaded - see the cdnjs <script> tag in rules.html/api.html).
 *
 * Rewrites cross-links between our own doc pages (RULES.md <-> rules.html,
 * API.md <-> api.html) so clicking a link inside the rendered content stays
 * on the nice rendered version instead of dropping into raw markdown text.
 * The raw .md files stay untouched and still resolve correctly when this
 * repo is browsed on GitHub, where the original relative links are meant
 * to work (e.g. RULES.md's own link to ../PROJECT_HANDOFF.md, which this
 * app doesn't serve at all - rewritten below to the GitHub source instead
 * of left dangling as a 404).
 */
async function renderMarkdownDoc(mdUrl, containerId) {
  const container = document.getElementById(containerId);
  try {
    const res = await fetch(mdUrl);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    let text = await res.text();

    text = text
      .replace(/\]\(RULES\.md\)/g, "](/rules.html)")
      .replace(/\]\(API\.md\)/g, "](/api.html)")
      .replace(
        /\]\(\.\.\/PROJECT_HANDOFF\.md\)/g,
        "](https://github.com/AmbiguousError/micro-diplomacy/blob/main/PROJECT_HANDOFF.md)"
      );

    container.innerHTML = marked.parse(text);
  } catch (err) {
    container.innerHTML = `
      <p class="text-rose-400">
        Couldn't load ${mdUrl} (${err.message}).
        <a href="${mdUrl}">View the raw file directly</a> instead.
      </p>`;
  }
}
