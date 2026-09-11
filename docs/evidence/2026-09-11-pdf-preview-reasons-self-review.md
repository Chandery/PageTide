# Self-review: PDF preview, scrollable hover card, specific reasons, simplified actions

Date: 2026-09-11 (UTC). Reviewer: implementing agent.

## Owner requests and what changed

| Request | Change |
|---|---|
| 悬停预览不能滑动，想直接在预览里看完摘要 | The preview now has `pointer-events:auto`, a `max-height` of ~74vh and an internally scrolling abstract. A 240ms grace period plus `mouseenter`/`mouseleave` on the preview keep it open while the pointer moves into it, so it can be scrolled; it still disappears when the pointer leaves |
| 详情只有摘要不够，要能看论文图/PDF；论文库也一样 | New `GET /api/pdf/view?key=` serves the stored PDF with `Content-Type: application/pdf` (inline) and `POST /api/pdf/prepare` fetches it first. The detail page embeds it in an inset `<iframe>`, with a "获取并预览 PDF" button when it is not downloaded yet. Library entries open the same detail page |
| 推荐理由都一样，要说清像哪篇/哪个方向 | New `explain()` compares the candidate against seeds and saved papers, and reports the nearest reference by name plus the shared topic terms, e.g. `与种子《DINO-WM…》方向接近；共同主题：ability, across, …`. OpenAlex `primary_topic` is now stored as `topic` and included as `领域：…` when available |
| 不要「以后再看 / 没空 / 看不懂」 | Removed from cards and the detail page; only 收藏 and 不感兴趣 remain. The backend actions are unchanged, so the "no activity ≠ dislike" rule still holds |

## Verified before committing

- 92 tests pass. New tests: `explain` names a saved reference and includes the topic; cards all carry a reason; `/api/pdf/view` 404s before download and serves bytes after.
- Live check on a fresh server:
  - each of the five cards produced a **different** reason naming a different seed and its shared terms;
  - `POST /api/pdf/prepare` fetched `.local/app/pdfs/2601.15282.pdf`; `GET /api/pdf/view` returned `application/pdf` starting with `%PDF-`;
  - `/api/detail` then reported `has_pdf: true`.

## Honest limits

- PDF preview only works for arXiv open-access papers; paywalled items return "no open-access PDF known".
- `topic` is only populated for newly fetched papers; older rows stay NULL until refreshed, in which case the reason falls back to seed/reference similarity.
- Hover-preview behaviour is CSS/JS logic I cannot visually verify; the grace period is heuristic.
- Recommendation quality is still unproven; quality gates remain `not_run`.
