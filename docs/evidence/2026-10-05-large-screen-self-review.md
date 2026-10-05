# Self-review: 2026-10-05-large-screen

Owner report: on an external display with the window maximised the text does not grow and the recommendations are squeezed into two columns inside a 1200 px page. Cause: the page width was fixed at 1200 px with a 2-column grid and fixed pixel font sizes.

Change: CSS only, no behaviour or data change. From 1700 px wide the page widens (1560 / 2000 / 2560 px at 1700 / 2200 / 2800 px), text sizes of the main page are multiplied by a step scale (1.2 / 1.45 / 1.8) and the recommendation grid gets 3 columns (4 from 2800 px), the library 2 (3). Under 1700 px nothing changes. The other pages (creation, map, project settings) get a wider container and a larger base size in the same steps.

Judgement calls: the steps are my guess at sensible sizes for 1080p / 1440p / 4K-looking-like-1440p displays, not measured against the owner's screen. I did not use CSS `zoom` because the project switcher and the reader compute sizes from the window size in JavaScript and a zoomed body would make those disagree; sizes of the most visible text are scaled one by one instead, so some smaller text (reader chrome, the knowledge-base page controls, the profile page) keeps its fixed size.

Not verified: the real external display and the Tauri window; whether the steps feel right.
